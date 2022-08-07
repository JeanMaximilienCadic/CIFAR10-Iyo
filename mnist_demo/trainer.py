from __future__ import print_function
import torch.nn.functional as F
from tqdm import tqdm
import torch
from sakura.ml import SakuraTrainer
from sakura import defaultMetrics
import os
from gnutools.fs import parent


class Trainer(SakuraTrainer):
    def __init__(self,
                 model,
                 optimizer,
                 scheduler,
                 metrics=defaultMetrics,
                 epochs=100,
                 model_path="mnist_cnn.pt",
                 checkpoint_path="mnist_cnn.ckpt.pt",
                 device="cuda",
                 device_test="cuda"):
        super(Trainer, self).__init__(model,
                                      optimizer,
                                      scheduler,
                                      metrics,
                                      epochs,
                                      model_path,
                                      checkpoint_path,
                                      device,
                                      device_test)

    def description(self):
        current, best = self._metrics.test.current, self._metrics.test.best
        suffix = f" | Acc: {current.accuracy:.4f} / ({best.accuracy:.4f})"
        suffix += f" | Loss:{current.loss:.4f} / ({best.loss:.4f})"
        return f"({self._epochs.best}) MNIST | Epoch: {self._epochs.current}/{self._epochs.total}{suffix}"

    def train(self, train_loader):
        if train_loader is not None:
            self._model.train()
            self._model.to(self._device)
            loader = train_loader
            current, best = self._metrics.train.current, self._metrics.train.best

            for batch_idx, (data, target) in tqdm(enumerate(loader), total=len(loader), desc=self.description()):
                self._optimizer.zero_grad()
                data, target = data.to(self._device), target.to(self._device)
                output = self._model(data)
                # Loss
                loss = F.nll_loss(output, target)
                loss.backward()
                current.loss += loss.item()
                # Accuracy
                pred = output.argmax(dim=1, keepdim=True)
                current.accuracy += pred.eq(target.view_as(pred)).sum().item()
                self._optimizer.step()
            self.update(current, best, loader)
            self._scheduler.step()

    def test(self, test_loader=None):
        if test_loader is not None:
            # Use a reference to the metrics
            self._model.eval()
            self._model.to(self._device_test)
            loader, correct = test_loader, 0
            current, best = self._metrics.test.current, self._metrics.test.best
            with torch.no_grad():
                for batch_idx, (data, target) in enumerate(loader):
                    data, target = data.to(
                        self._device_test), target.to(self._device_test)
                    output = self._model(data)
                    # Loss
                    current.loss += F.nll_loss(output,
                                               target, reduction='sum').item()
                    # Accuracy
                    pred = output.argmax(dim=1, keepdim=True)
                    current.accuracy += pred.eq(target.view_as(pred)
                                                ).sum().item()
            self.update(current, best, loader)
            self.checkpoint()

    def checkpoint(self):
        if self._metrics.test.current == self._metrics.test.best:
            os.makedirs(parent(self._model_path), exist_ok=True)
            torch.save(self._model.state_dict(), self._model_path)

    def run(self, train_loader=None, test_loader=None):
        for self._epoch in self._epochs:
            self.train(train_loader)
            self.test(test_loader)

    def update(self, current, best, loader):
        current.loss /= len(loader.dataset)
        current.accuracy = 100. * current.accuracy / len(loader.dataset)
        # Update the metrics
        try:
            assert best.accuracy is not None
            assert best.accuracy > current.accuracy
        except AssertionError:
            vars(best).update(vars(current))
            self._epochs.best = self._epochs.current
