"""Experimental differentiable prefix sharing. NOT used by the running trainer.

An input node is identified by its entire token prefix. Positions are original
prefix depths, and attention is restricted to ancestors. No context rewriting,
detached KV cache, sample selection, or change to loss denominators is permitted.
"""
from dataclasses import dataclass


@dataclass
class Layout:
    tokens: list
    positions: list
    parents: list
    # Each chain occupies [start, end); prefix lists its strict ancestors.
    chains: list
    queries: list
    targets: list

    @property
    def causal_pairs(self):
        return sum(d + 1 for d in self.positions)


def build_layout(actions):
    edges, tokens, parents, children, queries, targets = {}, [], [], [], [], []
    for prompt, response in actions:
        if not prompt or not response:
            raise ValueError('Original prompt and response must be nonempty')
        path, parent = [], -1
        for token in (list(prompt) + list(response))[:-1]:
            key = (parent, int(token))
            node = edges.get(key)
            if node is None:
                node = len(tokens)
                edges[key] = node
                tokens.append(int(token)); parents.append(parent); children.append([])
                if parent != -1:
                    children[parent].append(node)
            path.append(node); parent = node
        queries.append(path[len(prompt)-1:])
        targets.append(list(response))
        assert len(queries[-1]) == len(response)
    roots = [i for i, p in enumerate(parents) if p == -1]
    order, chain_old_ids, stack = [], [], list(reversed(roots))
    while stack:
        node = stack.pop(); chain = [node]
        while len(children[node]) == 1:
            node = children[node][0]; chain.append(node)
        order.extend(chain); chain_old_ids.append(chain)
        stack.extend(reversed(children[node]))
    renumber = {old: new for new, old in enumerate(order)}
    new_parents = [-1 if parents[i] == -1 else renumber[parents[i]] for i in order]
    positions = []
    for parent in new_parents:
        positions.append(0 if parent == -1 else positions[parent] + 1)
    chains = []
    for chain in chain_old_ids:
        start, end = renumber[chain[0]], renumber[chain[-1]] + 1
        prefix, parent = [], new_parents[start]
        while parent != -1:
            prefix.append(parent); parent = new_parents[parent]
        prefix.reverse()
        assert positions[start] == len(prefix)
        chains.append((start, end, prefix))
    return Layout([tokens[i] for i in order], positions, new_parents, chains,
                  [[renumber[i] for i in q] for q in queries], targets)


def prepare_layout(layout, device):
    import torch
    return [(start, end, torch.tensor(prefix + list(range(start, end)),
                                     dtype=torch.long, device=device))
            for start, end, prefix in layout.chains]


def bounded_layouts(actions, max_nodes=32000):
    """Split work, never tokens or samples. Original loss denominators still apply.

    A tree can exceed the longest individual context because it includes branches.
    Conservative bisection keeps original action order and caps each activation
    graph. It is a memory candidate, not a measured GPU-safe limit.
    """
    layout = build_layout(actions)
    if len(layout.tokens) <= max_nodes:
        return [layout]
    if len(actions) == 1:
        raise ValueError('A complete original action exceeds the candidate node budget')
    middle = len(actions)//2
    return bounded_layouts(actions[:middle], max_nodes) + bounded_layouts(actions[middle:], max_nodes)


def tree_attention(module, query, key, value, attention_mask, dropout=0.0,
                   scaling=None, tree_chains=None, **kwargs):
    import torch
    import torch.nn.functional as F
    from torch.nn.attention.bias import causal_lower_right
    if dropout != 0.0 or tree_chains is None or query.shape[0] != 1:
        raise ValueError('Tree path requires zero dropout, one tree, and explicit chains')
    outputs = []
    for start, end, indices in tree_chains:
        q = query[:, :, start:end]
        k = key.index_select(2, indices)
        v = value.index_select(2, indices)
        # Lower-right causal masking permits every query to attend its complete
        # prefix plus the causal part of its own chain. Ordinary is_causal=True
        # alone would incorrectly align a nonsquare matrix to its upper left.
        mask = causal_lower_right(end-start, indices.numel())
        outputs.append(F.scaled_dot_product_attention(
            q, k, v, attn_mask=mask, dropout_p=0.0, scale=scaling,
            enable_gqa=q.shape[1] != k.shape[1]))
    return torch.cat(outputs, dim=2).transpose(1, 2).contiguous(), None


def tree_logprobs(model, layout, chunk_size=128):
    import torch
    import torch.nn.functional as F
    from torch.utils.checkpoint import checkpoint
    from transformers.modeling_utils import ALL_ATTENTION_FUNCTIONS
    base = model.get_base_model() if hasattr(model, 'get_base_model') else model
    if base.config.model_type != 'qwen3' or base.config.attention_dropout != 0:
        raise ValueError('Only zero-dropout Qwen3 is tested')
    if any(getattr(m, 'p', 0) != 0 for m in model.modules() if isinstance(m, torch.nn.Dropout)):
        raise ValueError('Shared-prefix dropout masks would change the stochastic objective')
    ALL_ATTENTION_FUNCTIONS.register('experimental_prefix_tree', tree_attention)
    # A separate prototype model must be configured once before forward; the
    # backend must remain installed through checkpoint backward recomputation.
    base.config._attn_implementation = 'experimental_prefix_tree'
    device = next(model.parameters()).device
    ids = torch.tensor([layout.tokens], dtype=torch.long, device=device)
    pos = torch.tensor([layout.positions], dtype=torch.long, device=device)
    hidden = base.model(input_ids=ids, position_ids=pos,
                        attention_mask={'full_attention': None}, use_cache=False,
                        tree_chains=prepare_layout(layout, device), return_dict=True).last_hidden_state[0]
    result = []
    def logp(h, y):
        return -F.cross_entropy(base.lm_head(h).float(), y, reduction='none')
    for queries, targets in zip(layout.queries, layout.targets):
        h = hidden.index_select(0, torch.tensor(queries, device=device))
        y = torch.tensor(targets, device=device)
        chunks = []
        for start in range(0, len(targets), chunk_size):
            hc, yc = h[start:start+chunk_size], y[start:start+chunk_size]
            chunks.append(checkpoint(logp, hc, yc, use_reentrant=False)
                          if torch.is_grad_enabled() and hc.requires_grad else logp(hc, yc))
        result.append(torch.cat(chunks))
    return result
