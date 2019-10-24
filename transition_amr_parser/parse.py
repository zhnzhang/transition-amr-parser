# AMR parsing given a sentence and a model
import time
import os
import signal
import argparse
from collections import Counter

from tqdm import tqdm

from transition_amr_parser.state_machine import AMRStateMachine
from transition_amr_parser.io import (
    writer,
    read_tokenized_sentences,
    read_rule_stats,
)


# is_url_regex = re.compile('http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')


def argument_parser():

    parser = argparse.ArgumentParser(description='AMR parser')
    # Multiple input parameters
    parser.add_argument(
        "--in-sentences",
        help="file space with carriare return separated sentences",
        type=str
    )
    parser.add_argument(
        "--in-actions",
        help="file space with carriage return separated sentences",
        type=str
    )
    parser.add_argument(
        "--out-amr",
        help="parsing model",
        type=str
    )
    parser.add_argument(
        "--in-model",
        help="parsing model",
        type=str
    )
    parser.add_argument(
        "--in-rule-stats",
        help="alignment statistics needed for the rule component",
        type=str
    )
    parser.add_argument(
        "--verbose",
        help="verbose mode",
        action='store_true',
        default=False
    )
    parser.add_argument(
        "--step-by-step",
        help="pause after each action",
        action='store_true',
        default=False
    )
    parser.add_argument(
        "--pause-time",
        help="time waited after each step, default is manual",
        type=int
    )
    parser.add_argument(
        "--clear-print",
        help="clear command line before each print",
        action='store_true',
        default=False
    )
    parser.add_argument(
        "--offset",
        help="start at given sentence number (starts at zero)",
        type=int
    )
    parser.add_argument(
        "--random-up-to",
        help="sample randomly from a max number",
        type=int
    )

    args = parser.parse_args()

    # Argument pre-processing
    if args.random_up_to:
        import numpy as np
        args.offset = np.random.randint(args.random_up_to)

    # force verbose
    if not args.verbose:
        args.verbose = bool(args.step_by_step)

    # Sanity checks
    assert args.in_sentences or args.in_sentence_list
    assert args.in_actions or args.in_model
    # Not done yet
    if args.in_model:
        raise NotImplementedError()

    return args


def ordered_exit(signum, frame):
    """Mesage user when killing by signal"""
    print("\nStopped by user\n")
    exit(0)


def reduce_counter(counts, reducer):
    """
    Returns a new counter from an existing one where keys have been mapped
    to in  many-to-one fashion and counts added
    """
    new_counts = Counter()
    for key, count in counts.items():
        new_key = reducer(key)
        new_counts[new_key] += count
    return new_counts


class Statistics():

    def __init__(self):
        self.action_counts = Counter()
        self.action_tos_counts = Counter()

    def update(self, raw_action, state):
        if state.stack:
            stack0 = state.stack[-1]
            if stack0 in state.merged_tokens:
                tos_token = " ".join(
                    state.amr.tokens[i - 1]
                    for i in state.merged_tokens[stack0]
                )
            else:
                tos_token = state.amr.tokens[stack0 - 1]
            self.action_tos_counts.update([(raw_action, tos_token)])
        self.action_counts.update([raw_action])


def main():

    # Argument handling
    args = argument_parser()

    # Get data generators
    sentences = read_tokenized_sentences(args.in_sentences)
    if args.in_actions:
        actions = read_tokenized_sentences(args.in_actions)

    # set orderd exit
    if args.step_by_step:
        signal.signal(signal.SIGINT, ordered_exit)
        signal.signal(signal.SIGTERM, ordered_exit)

    # Get copy stats if provided
    if args.in_rule_stats:
        rule_stats = read_rule_stats(args.in_rule_stats)

    # Output AMR
    if args.out_amr:
        amr_write = writer(args.out_amr)

    sent_idx = -1
    statistics = Statistics()
    for sent_idx, sent_tokens in tqdm(enumerate(sentences)):

        # keep count of sentence index
        sent_idx += 1
        if args.offset and sent_idx < args.offset:
            continue

        # Initialize state machine
        amr_state_machine = AMRStateMachine(
            sent_tokens,
            rule_stats=rule_stats
        )

        # execute parsing model
        time_step = 0
        while amr_state_machine.stack or amr_state_machine.buffer:

            # Print state (pause if solicited)
            if args.verbose:
                pretty_machine_print(
                    sent_idx,
                    amr_state_machine,
                    args.clear_print,
                    args.step_by_step,
                    args.pause_time
                )

            # Get next action
            if args.in_actions:
                # externally provided actions
                raw_action = actions[sent_idx][time_step]
            else:
                # TODO: machine learning model / oracle
                pass

            # Collect statistics
            statistics.update(raw_action, amr_state_machine)

            # Update state machine
            amr_state_machine.applyAction(raw_action)

        # Output AMR
        if args.out_amr:
            amr_write(amr_state_machine.amr.toJAMRString())

    # close output AMR
    if args.out_amr:
        amr_write()


def pretty_machine_print(sent_idx, amr_state_machine, clear_print,
                         step_by_step, pause_time):
    if clear_print:
        # clean screen each time
        os.system('clear')
    print(f'sentence {sent_idx}\n')
    print(amr_state_machine)

    # step by step mode
    if step_by_step:
        if pause_time:
            time.sleep(pause_time)
        else:
            input('Press any key to continue')
