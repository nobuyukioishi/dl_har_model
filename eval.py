##################################################
# All functions related to evaluating a deep learning architecture using sensor-based activity data.
##################################################
# Author: Lloyd Pellatt
# Email: lp349@sussex.ac.uk
# Author: Marius Bock
# Email: marius.bock@uni-siegen.de
##################################################

import os
import time
from datetime import timedelta

import numpy as np
import torch
import wandb
from sklearn import metrics
from torch import nn
from torch.utils.data import DataLoader

from utils import AverageMeter, paint

train_on_gpu = torch.cuda.is_available()  # Check for cuda


def eval_model(model, eval_data, criterion=None, batch_size=256, seed=1):
    """
    Evaluate trained model.

    :param model: A trained model which is to be evaluated.
    :param eval_data: A SensorDataset containing the data to be used for evaluating the model.
    :param criterion: Citerion object which was used during training of model.
    :param batch_size: Batch size to use during evaluation.
    :param seed: Random seed which is employed.

    :return: loss, accuracy, f1 weighted and macro for evaluation data; if return_results, also predictions
    """

    if criterion is None:
        criterion = nn.CrossEntropyLoss()

    print(paint("Running HAR evaluation loop ..."))

    loader_test = DataLoader(eval_data, batch_size, False, pin_memory=True, worker_init_fn=np.random.seed(int(seed)))

    print("[-] Loading checkpoint ...")

    path_checkpoint = os.path.join(model.path_checkpoints, "checkpoint_best.pth")

    checkpoint = torch.load(path_checkpoint)
    model.load_state_dict(checkpoint["model_state_dict"])

    start_time = time.time()
    loss_test, acc_test, fm_test, fw_test, preds = eval_one_epoch(model, loader_test, criterion, True)

    print(
        paint(
            f"[-] Test loss: {loss_test:.2f}"
            f"\tacc: {100 * acc_test:.2f}(%)\tfm: {100 * fm_test:.2f}(%)\tfw: {100 * fw_test:.2f}(%)"
        )
    )

    elapsed = round(time.time() - start_time)
    elapsed = str(timedelta(seconds=elapsed))
    print(paint(f"Finished HAR evaluation loop (h:m:s): {elapsed}"))

    return loss_test, acc_test, fm_test, fw_test, elapsed, preds


def eval_one_epoch(model, loader, criterion, return_preds=False, return_pairs=False):
    """
    Train model for a one of epoch.

    :param model: A trained model which is to be evaluated.
    :param loader: A DataLoader object containing the data to be used for evaluating the model.
    :param criterion: The loss object.
    :param return_preds: Boolean indicating whether to return predictions or not.
    :param return_pairs: Boolean indicating whether to return pairs of predictions and targets or not.

    :return: loss, accuracy, f1 weighted and macro for evaluation data; if return_preds, also predictions
    """

    losses = AverageMeter("Loss")
    y_true, y_pred = [], []
    model.eval()

    with torch.no_grad():
        for batch_idx, (data, target, idx) in enumerate(loader):
            if train_on_gpu:
                data = data.cuda()
                target = target.cuda()

            z, logits = model(data)
            loss = criterion(logits, target.view(-1))
            losses.update(loss.item(), data.shape[0])
            probabilities = nn.Softmax(dim=1)(logits)
            _, predictions = torch.max(probabilities, 1)

            y_pred.append(predictions.cpu().numpy().reshape(-1))
            y_true.append(target.cpu().numpy().reshape(-1))

    # append invalid samples at the beginning of the test sequence
    if loader.dataset.prefix == "test":
        ws = data.shape[1] - 1
        samples_invalid = [y_true[0][0]] * ws
        y_true.append(samples_invalid)
        y_pred.append(samples_invalid)

    y_true = np.concatenate(y_true, 0)
    y_pred = np.concatenate(y_pred, 0)

    acc = metrics.accuracy_score(y_true, y_pred)
    fm = metrics.f1_score(y_true, y_pred, average="macro")
    fw = metrics.f1_score(y_true, y_pred, average="weighted")

    if return_preds:
        return losses.avg, acc, fm, fw, y_pred
    elif return_pairs:
        return losses.avg, acc, fm, fw, (y_true, y_pred)
    else:
        return losses.avg, acc, fm, fw
