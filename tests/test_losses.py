from .context import aorun

import numpy as np
import torch
from torch.autograd import Variable
from torch.nn import Parameter
import functools
from aorun.models import Model
from aorun.layers import ProbabilisticDense
from aorun.losses import mean_squared_error
from aorun.losses import binary_crossentropy
from aorun.losses import categorical_crossentropy
from aorun.losses import log_gaussian
from aorun.losses import variational_loss


def test_mse_variable():
    true = Variable(torch.Tensor([11, 11]))
    pred = Variable(torch.Tensor([10, 10]))

    loss = mean_squared_error(true, pred)

    assert type(loss) is Variable
    assert loss == 1


def test_mse_tensor():
    true = torch.Tensor([11, 11])
    pred = torch.Tensor([10, 10])
    loss = mean_squared_error(true, pred)
    assert loss == 1

    true = torch.Tensor([10, 10])
    pred = torch.Tensor([10, 10])
    loss = mean_squared_error(true, pred)
    assert loss == 0


def test_binary_crossentropy():
    true = torch.Tensor([1, 1, 1])

    loss = binary_crossentropy(true, true)
    assert loss == 0

    pred = torch.Tensor([[0, 0, 0]])
    loss = binary_crossentropy(true, pred)
    assert loss > 1


def test_categorical_crossentropy():
    true = torch.Tensor([[1, 0], [0, 1], [1, 0]])

    loss = categorical_crossentropy(true, true)
    assert loss == 0

    pred = torch.Tensor([[0, 1], [0, 1], [1, 0]])
    loss = categorical_crossentropy(true, pred)
    assert loss > 1


def test_log_gaussian():
    x = Variable(torch.Tensor([1, 1]))
    mu = Parameter(torch.Tensor([5, 3]))
    sigma = Parameter(torch.Tensor([4, 5]))
    loss = log_gaussian(x, mu, sigma)
    loss.mean().backward()
    assert np.all(loss.data.numpy() < 0)


def test_variational_loss():
    X = torch.randn(4, 4)
    true = Variable(torch.Tensor([[0, 1], [1, 0]]))
    pred = Variable(torch.Tensor([[0.4, 0.6], [0.1, 0.9]]))

    model = Model(
        ProbabilisticDense(10, input_dim=4),
        ProbabilisticDense(1)
    )

    ll = categorical_crossentropy
    variational_bayes = functools.partial(variational_loss,
                                          model=model,
                                          log_likelihood=ll)

    model.forward(X)
    loss = variational_bayes(true, pred)
    loss.backward()
    assert loss < 0