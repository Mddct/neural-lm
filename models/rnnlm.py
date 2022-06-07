from typing import Sequence, Tuple

import torch
from torch import nn

from models.adaptive_softmax import AdaptiveLogSoftmax
from models.label_smoothing import LabelSmoothingLoss
from models.rnn import StackedRNNLayer


class RNNEncoder(nn.Module):

    def __init__(
        self,
        vocab_size: int,
        n_layers: int,
        input_nodes: int,
        hidden_nodes: int,
        output_nodes: int,
        cell_type: str = "gru",
        dropout_rate: float = 0.0,
        adaptive_softmax: bool = False,
        cutoffs: Sequence[int] = [],
        div_value: float = 2.0,
    ) -> None:
        super().__init__()

        self.lookup_table = nn.Embedding(vocab_size, input_nodes)
        self.stacked_rnn = StackedRNNLayer(cell_type, input_nodes,
                                           hidden_nodes, output_nodes,
                                           n_layers, dropout_rate)
        self.adaptive_softmax = adaptive_softmax

        if adaptive_softmax:
            # TODO: dropout in adaptive sofmax
            self.log_softmax = AdaptiveLogSoftmax(output_nodes,
                                                  vocab_size,
                                                  cutoffs,
                                                  div_value,
                                                  head_bias=True)
        else:
            # TODO: tie embedding here
            self.out = nn.Linear(output_nodes, vocab_size)
            self.log_softmax = nn.LogSoftmax(dim=vocab_size)

    def forward(self, input: torch.Tensor, seq_len: torch.Tensor):
        """
        Args:
            input: [batch, time]
            seq_len: [batch]
        """

        # id to embedding
        embeddding = self.lookup_table(input)  # [bs, time, dim]

        max_seq_len = torch.max(seq_len)
        ids = torch.arange(0, max_seq_len, 1)  # [bs]
        padding = seq_len.unsqueeze(1) < ids  # [bs, max_seq_len]

        padding = padding.transpose(0, 1).unsqueeze(2)  #[time, bs, 1]
        embeddding = embeddding.transpose(0, 1)

        output = self.stacked_rnn(embeddding, padding)
        o, _ = output[0], output[1]

        if not self.adaptive_softmax:
            o = self.out(o)  #[time, bs, vocab_size]

        o = o.transpose(0, 1)  #[batch, time, vocab_size]
        o = self.log_softmax(o, dim=2)
        return o

    def forward_step(
        self, input: torch.Tensor, seq_len: torch.Tensor,
        state_m: torch.Tensor, state_c: torch.Tensor
    ) -> Tuple[torch.Tensor, Tuple[torch.Tensor, torch.Tensor]]:

        embeddding = self.lookup_table(input)  # [bs, time, dim]

        max_seq_len = torch.max(seq_len)
        ids = torch.arange(0, max_seq_len, 1)  # [bs]
        padding = seq_len.unsqueeze(1) < ids  # [bs, max_seq_len]

        padding = padding.transpose(0, 1).unsqueeze(2)  #[time, bs, 1]
        embeddding = embeddding.transpose(0, 1)

        output = self.stacked_rnn(embeddding, padding, (state_m, state_c))
        o, s = output[0], output[1]

        if not self.adaptive_softmax:
            o = self.out(o)  #[time, bs, vocab_size]
        o = o.transpose(0, 1)  #[batch, time, vocab_size]

        o = self.log_softmax(o)
        return o, s


class RNNLM(nn.Module):
    """
    """

    def __init__(
        self,
        vocab_size: int,
        lm_encoder: nn.Module,
        lsm_weight: float = 0.0,
        length_normalized_loss: bool = False,
    ):
        """Construct an gru cell object.
        """
        super().__init__()

        # TODO: lookup table
        self.model = lm_encoder
        self.length_normalized_loss = length_normalized_loss
        self.criterion = LabelSmoothingLoss(vocab_size, -1, lsm_weight,
                                            length_normalized_loss)

    def forward(self, input: torch.Tensor, input_length: torch.Tensor,
                labels: torch.Tensor, labels_length: torch.Tensor):
        """
        Args:
            input (torch.Tensor):  [batch, time].
            input_len: [bs]
            labels: [bs, time] -1 is ignore id
            labels_length: [bs]
        Returns:
            loss (torch.Tensor): float scalar tensor  Note: before batch average
            ppl (torch.Tensor) : [batch] Note: before batch average
            total_ppl (torch.Tensor) : flaot scalar tensor
        """

        assert (input.shape[0] == input_length.shape[0] == labels.shape[0] ==
                labels_length.shape[0]), (input.shape, input_length.shape,
                                          labels.shape, labels_length.shape)
        # logit after sofmax
        logit = self.model(input, input_length)  #[bs, time_stamp, vocab]
        loss, each_seq_loss_in_batch = self.criterion(logit, labels)
        total_ppl = loss.exp(
        ) if self.length_normalized_loss else loss * input.size(
            0) / labels_length.sum()

        ppl = each_seq_loss_in_batch.exp()
        return loss, ppl, total_ppl

    @torch.jit.export
    def forward_step(
        self, input: torch.Tensor, seq_len: torch.Tensor,
        state_m: torch.Tensor, state_c: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:

        o, s = self.model.forward_step(input, seq_len, state_m, state_c)
        return o, s[0], s[1]
