import math
import numpy as np
import torch
from torch.autograd import Variable
from torch.nn import Parameter
from torch.nn import Conv2d as TorchConv2D
from torch.nn import RNN as TorchRecurrent
from torch.nn import Linear as TorchDense
from . import activations
from . import initializers
from . import utils


class Layer(object):

    def __init__(self, input_dim=None, init='glorot_uniform'):
        self.input_dim = input_dim
        self.init = initializers.get(init)

    def forward(self, X):
        X = utils.to_variable(X)
        return X

    def build(self, input_dim):
        self.output_dim = input_dim

    @property
    def params(self):
        return tuple()


class Activation(Layer):

    def __init__(self, activation, *args, **kwargs):
        super(Activation, self).__init__(*args, **kwargs)
        self.activation = activations.get(activation)

    def forward(self, X):
        X = super(Activation, self).forward(X)
        return self.activation(X)


class Dense(Layer):

    def __init__(self, units, *args, **kwargs):
        super(Dense, self).__init__(*args, **kwargs)
        self.units = units
        self.output_dim = units
        if self.input_dim:
            self.build(self.input_dim)

    @property
    def params(self):
        return list(self.layer.parameters())

    def build(self, input_dim):
        assert type(input_dim) is int
        self.input_dim = input_dim
        self.layer = TorchDense(self.input_dim, self.units)

    def forward(self, X):
        X = super(Dense, self).forward(X)
        return self.layer.forward(X)


class ProbabilisticDense(Layer):

    def __init__(self, units, init='glorot_uniform', *args, **kwargs):
        super(ProbabilisticDense, self).__init__(*args, **kwargs)
        self.units = units
        self.output_dim = units
        self.init = initializers.get(init)
        if self.input_dim:
            self.build(self.input_dim)

    @property
    def params(self):
        return (self.W_mu, self.W_rho, self.b_mu, self.b_rho)

    def build(self, input_dim):
        self.input_dim = input_dim
        W_shape = [self.input_dim, self.output_dim]
        b_shape = [self.output_dim]
        self.W_mu = self.init(W_shape, self.input_dim, self.output_dim)
        self.W_rho = self.init(W_shape, self.input_dim, self.output_dim)
        self.b_mu = self.init(b_shape, self.input_dim, self.output_dim)
        self.b_rho = self.init(b_shape, self.input_dim, self.output_dim)

    def forward(self, X):
        X = super(ProbabilisticDense, self).forward(X)
        sigma_prior = math.exp(-3)
        W_eps = Variable(torch.zeros(self.input_dim, self.output_dim))
        W_eps = torch.normal(W_eps, std=sigma_prior)
        self.W = W = self.W_mu + torch.log1p(torch.exp(self.W_rho)) * W_eps
        b_eps = Variable(torch.zeros(self.output_dim))
        b_eps = torch.normal(b_eps, std=sigma_prior)
        self.b = b = self.b_mu + torch.log1p(torch.exp(self.b_rho)) * b_eps
        XW = X @ W
        return XW + b.expand_as(XW)


class Conv2D(Layer):

    def __init__(self, filters, kernel_size, stride=1, *args, **kwargs):
        super(Conv2D, self).__init__(*args, **kwargs)
        self.filters = filters
        self.kernel_size = kernel_size
        self.stride = stride
        if self.input_dim is not None:
            self.build(self.input_dim)

    @property
    def params(self):
        return list(self.layer.parameters())

    def build(self, input_dim):
        input_dim = list(input_dim)
        assert len(input_dim) >= 2
        if len(input_dim) == 2:
            in_channels = 1
            input_dim = [1] + input_dim
        else:
            in_channels = input_dim[0]
        self.input_dim = input_dim
        d1 = (input_dim[1] - self.kernel_size[0]) / self.stride + 1
        d2 = (input_dim[2] - self.kernel_size[1]) / self.stride + 1
        self.output_dim = [self.filters, d1, d2]
        self.layer = TorchConv2D(in_channels, self.filters,
                                 kernel_size=self.kernel_size,
                                 stride=self.stride)

    def forward(self, X):
        X = super(Conv2D, self).forward(X)
        X = X.view(-1, *self.input_dim)
        return self.layer.forward(X)


class Dropout(Layer):

    def __init__(self, p=0.5, *args, **kwargs):
        super(Dropout, self).__init__(*args, **kwargs)
        self.p = p

    def forward(self, X):
        X = super(Dropout, self).forward(X)
        eps = torch.Tensor(*X.size())
        eps.fill_(self.p)
        eps = Variable(torch.bernoulli(eps))
        return X * eps


class Recurrent(Layer):

    def __init__(self, units, length, stateful=False, *args, **kwargs):
        super(Recurrent, self).__init__(*args, **kwargs)
        self.units = units
        self.length = length
        self.output_dim = [length, units]
        self.stateful = stateful
        self.states = None
        if self.input_dim is not None:
            self.build(self.input_dim)

    @property
    def params(self):
        return list(self.layer.parameters())

    def build(self, input_dim):
        self.input_dim = input_dim
        self.layer = TorchRecurrent(self.input_dim, self.units, self.length)

    def clear_states(self):
        self.states = None

    def forward(self, X):
        X = super(Recurrent, self).forward(X)
        if self.stateful and self.states is not None:
            outputs, self.states = self.layer.forward(X, self.states)
        else:
            outputs, self.states = self.layer.forward(X)

        return outputs


class Flatten(Layer):

    def __init__(self, *args, **kwargs):
        super(Flatten, self).__init__(*args, **kwargs)

    def build(self, input_dim):
        self.input_dim = input_dim
        self.output_dim = int(np.prod(input_dim))

    def forward(self, X):
        X = super(Flatten, self).forward(X)
        X = X.view(X.size()[0], self.output_dim)
        return X


class TimeDistributed(object):

    def __init__(self, layer):
        self.layer = layer

    @property
    def params(self):
        return self.layer.params

    def build(self, input_dim):
        length, dim = input_dim
        return self.layer.build(dim)

    def forward(self, X):
        batch_size, length, dim = X.size()
        out = self.layer.forward(X.view(batch_size * length, dim))
        return out.view(batch_size, length, out.size(1))
