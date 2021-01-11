# Standalone AMR parser from an existing trained APT model

import os
import math
import copy

from tqdm import tqdm
import torch
from fairseq import checkpoint_utils, utils
from fairseq.models.roberta import RobertaModel
from fairseq.tokenizer import tokenize_line

from fairseq_ext import options    # this is key to recognizing the customized arguments
from fairseq_ext.roberta.pretrained_embeddings import PretrainedEmbeddings
from fairseq_ext.data.amr_action_pointer_dataset import collate
# OR (same results) from fairseq_ext.data.amr_action_pointer_graphmp_dataset import collate
from fairseq_ext.utils import post_process_action_pointer_prediction, clean_pointer_arcs
from transition_amr_parser.o8_state_machine import AMRStateMachine, get_spacy_lemmatizer
from transition_amr_parser.amr import InvalidAMRError, get_duplicate_edges
from transition_amr_parser.utils import yellow_font


def load_models_and_task(args, use_cuda, task=None):
    # if `task` is not provided, it will be from the saved model args
    models, model_args, task = checkpoint_utils.load_model_ensemble_and_task(
        args.path.split(':'),
        arg_overrides=eval(args.model_overrides),
        task=task,
    )
    # Optimize ensemble for generation
    for model in models:
        model.make_generation_fast_(
            beamable_mm_beam_size=None if args.no_beamable_mm else args.beam,
            need_attn=args.print_alignment,
        )
        if args.fp16:
            print('using fp16 for models')
            model.half()
        if use_cuda:
            print('using GPU for models')
            model.cuda()
        else:
            print('using CPU for models')

    # model = Model(models, task.target_dictionary)
    return models, model_args, task


def load_args_from_config(config_path):
    """Load args from bash configuration scripts"""
    # TODO there might be better ways; e.g. source the bash script in python and use $BERT_LAYERS directly
    config_dict = {}
    with open(config_path, 'r') as f:
        for line in f:
            if line.strip():
                if not line.startswith('#') and '=' in line:
                    kv = line.strip().split('#')[0].strip().split('=')
                    assert len(kv) == 2
                    config_dict[kv[0]] = kv[1].replace('"', '')    # remove the " in bach args
    return config_dict


def load_roberta(name=None, roberta_cache_path=None, roberta_use_gpu=False):
    if not roberta_cache_path:
        # Load the Roberta Model from torch hub
        roberta = torch.hub.load('pytorch/fairseq', name)
    else:
        roberta = RobertaModel.from_pretrained(
            roberta_cache_path,
            checkpoint_file='model.pt'
        )
    roberta.eval()
    if roberta_use_gpu:
        roberta.cuda()
    return roberta


class AMRParser:
    def __init__(
        self,
        models,           # PyTorch model
        task,             # fairseq task
        src_dict,         # fairseq dict
        tgt_dict,         # fairseq dict
        machine_rules,    # path to train.rules.json
        machine_type,     # AMR, NER, etc
        use_cuda,         #
        args,             # args for decoding
        model_args,       # args read from the saved model checkpoint
        to_amr=True,      # whether to output the final AMR graph
        entities_with_preds=None,        # special entities in the data oracle
        embeddings=None,  # PyTorch RoBERTa model (if dealing with token input)
        inspector=None    # function to call after each step
    ):

        # member variables
        self.models = models
        self.task = task
        self.use_cuda = use_cuda
        self.src_dict = src_dict
        self.tgt_dict = tgt_dict
        self.embeddings = embeddings
        self.inspector = inspector

        self.machine_rules = machine_rules
        self.machine_type = machine_type

        self.args = args
        self.model_args = model_args

        self.generator = self.task.build_generator(args, model_args)

        self.to_amr = to_amr
        if to_amr:
            # Initialize lemmatizer as this is slow
            self.lemmatizer = get_spacy_lemmatizer()
            self.entities_with_preds = entities_with_preds

    @classmethod
    def default_args(cls, checkpoint=None, fp16=False):
        """Default args for generation"""
        default_args = ['dummy_data_folder',
                        '--emb-dir', 'dummy_emb_dir',
                        '--user-dir', '../fairseq_ext',
                        '--task', 'amr_action_pointer',    # this is dummy; will be updated by the model args
                        '--modify-arcact-score', '1',
                        '--use-pred-rules', '0',
                        '--beam', '1',
                        '--batch-size', '128',
                        '--remove-bpe',
                        '--path', checkpoint or 'dummy_model_path',
                        '--quiet',
                        '--results-path', 'dummy_results_path',
                        '--machine-type', 'AMR',        # not currently used
                        '--machine-rules', 'dummy']     # not currently used
        if fp16:
            default_args.append('--fp16')
        return default_args


    @classmethod
    def from_checkpoint(cls, checkpoint, dict_dir=None, roberta_cache_path=None,
                        fp16=False,
                        inspector=None):
        '''
        Initialize model from checkpoint
        '''

        # ===== load default args: some are dummy =====
        parser = options.get_interactive_generation_parser()
        default_args = cls.default_args(checkpoint, fp16=fp16)    # model path set here
        args = options.parse_args_and_arch(parser, input_args=default_args)
        utils.import_user_module(args)
        # when `input_args` is fed in, it overrides the command line input args
        # only one required positional argument for the argparser: data
        if args.max_tokens is None and args.max_sentences is None:
            args.max_tokens = 12000

        # debug
        # print(args)
        # breakpoint()

        # ===== load model (ensemble), further model args, and the fairseq task =====
        if dict_dir is not None:
            args.model_overrides = f'{{"data": "{dict_dir}"}}'
            # otherwise, the default dict folder is read from the model args
        use_cuda = torch.cuda.is_available() and not args.cpu
        models, model_args, task = load_models_and_task(args, use_cuda, task=None)
        # task loads in the dictionaries:
        # task.src_dict
        # task.tgt_dict

        # # for back compatibility
        # if not hasattr(model_args, 'shift_pointer_value'):
        #     model_args.shift_pointer_value = 1

        # ===== load pretrained Roberta model for source embeddings =====
        # need "pretrained_embed" and "bert_layers"
        if model_args.pretrained_embed_dim == 768:
            pretrained_embed = 'roberta.base'
        elif model_args.pretrained_embed_dim == 1024:
            pretrained_embed = 'roberta.large'
        else:
            raise ValueError

        checkpoint_folder = os.path.dirname(checkpoint.split(':')[0])
        model_folder = os.path.dirname(checkpoint_folder)
        config_data_path = None
        for dfile in os.listdir(model_folder):
            if dfile.startswith('config_data'):
                config_data_path = dfile
                break
        if config_data_path is None:
            raise ValueError('data configuration file not found')
        else:
            config_data_path = os.path.join(model_folder, config_data_path)

        config_data_dict = load_args_from_config(config_data_path)
        bert_layers = list(map(int, config_data_dict['BERT_LAYERS'].split()))

        embeddings = PretrainedEmbeddings(name=pretrained_embed,
                                          bert_layers=bert_layers,
                                          model=load_roberta(name=pretrained_embed,
                                                             roberta_cache_path=roberta_cache_path,
                                                             roberta_use_gpu=use_cuda))

        print("Finished loading models")

        # ===== load other args =====
        # TODO adapt to the new path organization, or allow feeding from outside
        machine_type = args.machine_type
        machine_rules = os.path.join(config_data_dict['ROOTDIR'], config_data_dict['ORACLEDIR'],
                                     'oracle', 'train.rules.json')
        assert os.path.isfile(machine_rules), f"Missing {machine_rules}"
        args.machine_rules = machine_rules

        entities_with_preds = config_data_dict['ENTITIES_WITH_PREDS'].split(',')

        return cls(models,task, task.src_dict, task.tgt_dict, machine_rules, machine_type,
                   use_cuda, args, model_args, to_amr=True, entities_with_preds=entities_with_preds,
                   embeddings=embeddings, inspector=inspector)

    def get_bert_features_batched(self, sentences, batch_size):
        bert_data = []
        num_batches = math.ceil(len(sentences)/batch_size)
        for i in tqdm(range(0, num_batches), desc='roberta'):
            batch = sentences[i * batch_size: i * batch_size + batch_size]
            batch_data = self.embeddings.extract_batch(batch)
            for i in range(0, len(batch)):
                bert_data.append((
                    copy.deepcopy(batch_data["word_features"][i]),
                    copy.deepcopy(batch_data["wordpieces_roberta"][i]),
                    copy.deepcopy(
                        batch_data["word2piece_scattered_indices"][i]
                    )
                ))
        print(len(bert_data))
        assert len(bert_data) == len(sentences)
        return bert_data

    def get_token_ids(self, sentence):
        return self.src_dict.encode_line(
            line=sentence,
            line_tokenizer=tokenize_line,
            add_if_not_exist=False,
            append_eos=False,
            reverse_order=False
        )

    def convert_sentences_to_data(self, sentences, batch_size,
                                  roberta_batch_size):

        # extract RoBERTa features
        roberta_features = \
            self.get_bert_features_batched(sentences, roberta_batch_size)

        # organize data into a fairseq batch
        data = []
        for index, sentence in enumerate(sentences):
            ids = self.get_token_ids(sentence)
            word_features, wordpieces_roberta, word2piece_scattered_indices =\
                roberta_features[index]
            data.append({
                'id': index,
                'source': ids,
                'source_fix_emb': word_features,
                'src_wordpieces': wordpieces_roberta,
                'src_wp2w': word2piece_scattered_indices,
                'src_tokens': tokenize_line(sentence)    # original source tokens
            })
        return data

    def get_iterator(self, samples, batch_size):
        batches = []
        for i in range(0, math.ceil(len(samples)/batch_size)):
            sample = samples[i * batch_size: i * batch_size + batch_size]
            batch = collate(
                samples, pad_idx=self.tgt_dict.pad(),
                eos_idx=self.tgt_dict.eos(),
                left_pad_source=True,
                left_pad_target=False,
                input_feeding=True,
                collate_tgt_states=False
            )
            batches.append(batch)
        return batches

    def parse_batch(self, sample, to_amr=True):
        # parse a batch of data
        # following generate.py

        hypos = self.task.inference_step(self.generator, self.models, sample, self.args, prefix_tokens=None)

        assert self.args.nbest == 1, 'Currently we only support outputing the top predictions'

        predictions = []

        for i, sample_id in enumerate(sample['id'].tolist()):
            src_tokens = sample['src_sents'][i]
            target_tokens = None

            for j, hypo in enumerate(hypos[i][:self.args.nbest]):
                # args.nbest is default 1, i.e. saving only the top predictions
                actions_nopos, actions_pos, actions = post_process_action_pointer_prediction(hypo, self.tgt_dict)

                if self.args.clean_arcs:    # this is 0 by default
                    actions_nopos, actions_pos, actions, invalid_idx = clean_pointer_arcs(actions_nopos,
                                                                                          actions_pos,
                                                                                          actions)

                if to_amr:
                    machine = AMRStateMachine(tokens=src_tokens, amr_graph=True,
                                              spacy_lemmatizer=self.lemmatizer,
                                              entities_with_preds=self.entities_with_preds)
                    # CLOSE action is internally managed
                    machine.apply_actions(actions if actions[-1] == 'CLOSE' else actions + ['CLOSE'])
                else:
                    machine = None

                predictions.append({
                    'actions_nopos': actions_nopos,
                    'actions_pos': actions_pos,
                    'actions': actions,
                    'reference': target_tokens,
                    'src_tokens': src_tokens,
                    'sample_id': sample_id,
                    'machine': machine
                })

        return predictions

    def parse_sentences(self, batch, batch_size=128, roberta_batch_size=10):
        """parse a list of sentences.

        Args:
            batch (List[List[str]]): list of tokenized sentences.
            batch_size (int, optional): batch size. Defaults to 128.
            roberta_batch_size (int, optional): RoBerta batch size. Defaults to 10.
        """
        # max batch_size
        if len(batch) < batch_size:
            batch_size = len(batch)
        print("Running on batch size: " + str(batch_size))

        sentences = []
        # The model expects <ROOT> token at the end of the input sentence
        for tokens in batch:
            if tokens[-1] != "<ROOT>":
                tokens.append("<ROOT>")
            sentences.append(" ".join(tokens))

        data = self.convert_sentences_to_data(sentences, batch_size,
                                              roberta_batch_size)
        data_iterator = self.get_iterator(data, batch_size)

        # Loop over batches of sentences
        amr_annotations = {}
        for sample in tqdm(data_iterator, desc='decoding'):
            # move to device
            sample = utils.move_to_cuda(sample) if self.use_cuda else sample

            if 'net_input' not in sample:
                raise Exception("Did not expect empty sample")
                continue

            # parse for this data batch
            predictions = self.parse_batch(sample, to_amr=self.to_amr)

            # collect all annotations
            if not self.to_amr:
                continue

            for pred_dict in predictions:
                sample_id = pred_dict['sample_id']
                machine = pred_dict['machine']
                try:
                    amr_annotations[sample_id] = machine.get_annotations()
                except InvalidAMRError as exception:
                    print(f'\nFailed at sentence {sample_id}\n')
                    raise exception

                # sanity check annotations
                dupes = get_duplicate_edges(machine.amr)
                if any(dupes):
                    msg = yellow_font('WARNING:')
                    print(f'{msg} duplicated edges in sent {sample_id}', end=' ')
                    print(dict(dupes))
                    print(' '.join(pred_dict['src_tokens']))

        # return the AMRs in order
        results = []
        for i in range(0, len(batch)):
            results.append(amr_annotations[i])

        return results, predictions
