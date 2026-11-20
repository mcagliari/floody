#!/usr/bin/env python
''' Optuna hyper-parameter search for the outcome flow q(Y|X) (`flow`) or the
support flow p(X) (`support`) of one treatment arm.

The objective is the loss on an external validation set, split from the
training data by `--split-by` (random rows, zipcode or event); the flows'
internal early-stopping split stays random. Study files: `causalflow.study`.

example:
    python train_causalflow.py flow control flow.control.zipcode -d $SCRATCH/floody/flow --split-by zipcode
'''
import argparse
from importlib.metadata import version

import torch
import optuna
from floody import data as D
from causalflow import causalflow
from causalflow import support as Support
from causalflow import study as Study

# log10 claim range; not yet reconciled with [0, 6] used elsewhere (floody Plan)
OUTCOME_RANGE = [[-1.], [6.]]


def flow_objective(train, val, device, study_dir, study_name, max_epochs=None):
    ''' objective for the outcome flow; `made` (sbi 0.25) only uses the number
    of hidden features and of mixture components among its architecture
    arguments, so only those are searched (plus the learning rate).
    '''
    (Y, X, _), (Y_val, X_val, _) = train, val
    train_kwargs = {} if max_epochs is None else {'max_num_epochs': max_epochs}

    def objective(trial):
        n_hidden = trial.suggest_int("n_hidden", 32, 128, log=True)
        n_comp = trial.suggest_int("n_comp", 1, 5)
        lr = trial.suggest_float("lr", 5e-6, 1e-3, log=True)

        cflow = causalflow.CausalFlowA(device=device)
        cflow.set_architecture(arch='made', nhidden=n_hidden, num_mixture_components=n_comp)
        flow, internal_loss = cflow._train_flow(Y, X, outcome_range=OUTCOME_RANGE,
                training_batch_size=50, learning_rate=lr, seed=trial.number, **train_kwargs)

        trial.set_user_attr('internal_loss', float(internal_loss))
        torch.save(flow, Study.trial_file(study_dir, study_name, trial.number))
        return cflow.validation_loss(flow, Y_val, X_val)
    return objective


def support_objective(train, val, device, study_dir, study_name, max_epochs=None):
    ''' objective for the support flow (nflows MAF) '''
    (_, X, _), (_, X_val, _) = train, val

    def objective(trial):
        n_blocks = trial.suggest_int("n_blocks", 2, 5)
        n_hidden = trial.suggest_int("n_hidden", 32, 128, log=True)
        lr = trial.suggest_float("lr", 5e-6, 1e-3, log=True)

        torch.manual_seed(trial.number)     # weight initialization
        sup = Support.Support(device=device)
        sup.set_architecture(X.shape[1], nhidden=n_hidden, nblock=n_blocks)
        flow, internal_loss = sup._train(X, batch_size=50, learning_rate=lr,
                num_iter=300 if max_epochs is None else max_epochs, clip_max_norm=1)

        trial.set_user_attr('internal_loss', float(internal_loss))
        torch.save(flow, Study.trial_file(study_dir, study_name, trial.number))
        return sup.validation_loss(flow, X_val)
    return objective


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("model", choices=['flow', 'support'])
    parser.add_argument("sample", choices=['treated', 'control'])
    parser.add_argument("study", help="optuna study name (new name for every setup)")
    parser.add_argument("-d", "--dir", required=True, help="directory of the studies")
    parser.add_argument("--split-by", default='random', choices=['random', 'zipcode', 'event'])
    parser.add_argument("--split-seed", type=int, default=42)
    parser.add_argument("--n-trials", type=int, default=1000)
    parser.add_argument("--max-epochs", type=int, default=None, help="cap on training epochs (tests)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    val_fraction, test_fraction = 0.1, 0.1

    parts = D.FEMA().prepare(split_by=args.split_by, val_fraction=val_fraction,
                             test_fraction=test_fraction, seed=args.split_seed)
    train, val = parts['train'][args.sample], parts['val'][args.sample]
    if args.verbose: print('Ntrain = %i, Nval = %i' % (len(train[0]), len(val[0])))

    make = flow_objective if args.model == 'flow' else support_objective
    objective = make(train, val, device, args.dir, args.study, max_epochs=args.max_epochs)

    setup = {'model': args.model, 'sample': args.sample, 'split_by': args.split_by,
             'split_seed': args.split_seed, 'val_fraction': val_fraction,
             'test_fraction': test_fraction, 'n_train': len(train[0]), 'n_val': len(val[0]),
             'arch': 'sbi made' if args.model == 'flow' else 'nflows MAF',
             'outcome_range': OUTCOME_RANGE if args.model == 'flow' else None,
             'max_epochs': args.max_epochs,
             'versions': {p: version(p) for p in ('torch', 'sbi', 'nflows', 'optuna')}}

    sampler = optuna.samplers.TPESampler(n_startup_trials=20, constant_liar=True)
    study = optuna.create_study(study_name=args.study, sampler=sampler, direction="minimize",
                                storage=Study.storage(args.dir, args.study), load_if_exists=True)
    # resuming is fine, mixing setups in one study is not
    if study.user_attrs and study.user_attrs != setup:
        raise ValueError('study %s exists with a different setup: %s' % (args.study, study.user_attrs))
    for key, value in setup.items():
        study.set_user_attr(key, value)

    study.optimize(objective, n_trials=args.n_trials)
    print("  Number of finished trials: %i" % len(study.trials))


if __name__ == "__main__":
    main()
