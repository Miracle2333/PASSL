# Copyright (c) 2023 PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import paddle
import paddle.distributed as dist
from paddle.distributed.communication.group import _get_or_throw_group_rank
from paddle.autograd import PyLayer


def split(tensor, axis=0, group=None):
    return _Split.apply(tensor, axis, group)

def all_gather(tensor, group=None):
    """
    Gathers tensors from the whole group in a list.

    Arguments:
        tensor (Tensor): Tensor to be broadcast from current process.
        group (ProcessGroup, optional): The process group to work on.

    Returns:
        tuple([Tensor]): Output of the collective.

    """
    return _AllGather.apply(tensor, group)


class _Split(PyLayer):
    @staticmethod
    def forward(ctx, tensor, axis, group):
        ctx.group = group
        ctx.axis = axis

        rank = dist.get_rank()
        src_rank_in_group = group.get_group_rank(rank)
        out = paddle.split(tensor, group.nranks, axis=axis)[src_rank_in_group]

        return out

    @staticmethod
    def backward(ctx, grad_output):
        tensor_list = []
        dist.all_gather(tensor_list, grad_output, group=ctx.group)
        grad = paddle.concat(tensor_list, axis=ctx.axis)
        return grad


class _Reduce_Scatter(PyLayer):
    @staticmethod
    def forward(ctx, tensor, group, *input_tensor_list):
        ctx.group = group
        dist.reduce_scatter(tensor, list(input_tensor_list), group=group)
        return tensor

    @staticmethod
    def backward(ctx, grad_output):
        return (None) + _AllGather.apply(grad_output, ctx.group)


class _AllGather(PyLayer):
    @staticmethod
    def forward(ctx, tensor, group):
        ctx.group = group

        out_tensor_list = []
        dist.all_gather(out_tensor_list, tensor, group=group)
        return tuple(out_tensor_list)

    @staticmethod
    def backward(ctx, *grad_outputs):
        rank = dist.get_rank()
        src_rank_in_group = ctx.group.get_group_rank(rank)
        gx = paddle.empty_like(grad_outputs[src_rank_in_group])
        _Reduce_Scatter.apply(gx, ctx.group, *grad_outputs)
        return gx
