"""SchemaMem L3 core: entity-centric attributed graph with per-slot changepoint
arbitration. This module is the belief-evolution engine (no LLM here).

Layers upstream (L0 turns -> L1 facts -> L2 observations) produce Observation
objects; this module consumes an ordered stream of them per slot and routes each
to one of the memory actions:

    ASSIMILATE   - low prediction error, value matches current belief
    ACCUMULATE   - violation, candidate has < k independent-episode votes
    ACCOMMODATE  - candidate reaches >= k votes -> belief rewritten, old -> superseded
    PROTECT      - isolated violation, no corroboration -> kept verbatim as exception.
                   Emitted by finalize() (a stream-end sweep), NOT returned by
                   ingest(): an isolated violation is routed ACCUMULATE at ingest
                   time and only becomes a protected exception once the stream
                   ends without reaching k votes.
    DISSOLVE     - orthogonal (reconstructability) criterion, handled separately;
                   not emitted by this module yet.

Only ASSIMILATE / ACCUMULATE / ACCOMMODATE are returned by ingest(). The
prediction-error scoring (surprise) and candidate semantic merging are supplied
by the caller (an LLM in the full system, a stub in tests). This file only
decides, given (candidate_id, pred_error, episode_id), which action fires.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable


class Action(str, Enum):
    ASSIMILATE = "ASSIMILATE"
    ACCUMULATE = "ACCUMULATE"
    ACCOMMODATE = "ACCOMMODATE"
    PROTECT = "PROTECT"
    DISSOLVE = "DISSOLVE"


@dataclass
class Observation:
    """L2 output: one slot-level datum aligned to schema coordinates.

    candidate_id groups surface variants that mean the same thing
    ('started fish' / 'salmon' / 'pescatarian' -> 'fish'); supplied upstream by
    the semantic-merge step. pred_error in [0,1]: 0 = matches belief, 1 = strong
    violation. None candidate_id + low pred_error means 'congruent with belief'.
    """
    entity: str
    slot: str
    value: str
    pred_error: float
    episode_id: str
    t: str
    candidate_id: Optional[str] = None   # None => congruent with current belief
    source_fact: str = ""
    forgettable: bool = False            # set True when DISSOLVE releases the raw text


@dataclass
class Candidate:
    """A proposed new value for a slot, accumulating cross-episode support."""
    candidate_id: str
    votes: set = field(default_factory=set)           # distinct episode_ids
    observations: list = field(default_factory=list)  # Observation rows
    last_episode_idx: int = -1                        # order idx of most recent vote (for decay)


@dataclass
class Slot:
    name: str
    belief: Optional[str] = None
    belief_t: Optional[str] = None
    superseded: list = field(default_factory=list)     # [(old_value, t)]
    exceptions: list = field(default_factory=list)      # [Observation]
    ledger: list = field(default_factory=list)          # [Observation] all seen
    candidates: dict = field(default_factory=dict)      # candidate_id -> Candidate
    won_lines: set = field(default_factory=set)         # candidate_ids that became belief
    forgotten: int = 0                                  # # raw episodes released by DISSOLVE (ε)

    def vote_count(self, candidate_id: str) -> int:
        c = self.candidates.get(candidate_id)
        return len(c.votes) if c else 0


@dataclass
class Schema:
    """One entity's schema: named slots, each with its own evidence + belief."""
    entity: str
    slots: dict = field(default_factory=dict)           # slot_name -> Slot

    def get_slot(self, name: str) -> Slot:
        if name not in self.slots:
            self.slots[name] = Slot(name=name)
        return self.slots[name]


# ----- accommodation: rewrite the belief into a clean expectation -----
# In the full system this is an LLM call ('strict-veg' + 'fish' -> 'pescatarian').
# Default here just adopts the triggering candidate's latest value, so the core
# is testable without an LLM; callers pass their own rewriter.
def _default_rewriter(old_belief: Optional[str], candidate: Candidate) -> str:
    return candidate.observations[-1].value


class SchemaGraph:
    """The L3 graph + the changepoint arbitration engine.

    k: distinct independent episodes a candidate needs to trigger accommodation.
    An isolated violation that never reaches k, and is not the currently winning
    line of evidence, is flushed to the exception store by `finalize()`.
    """

    def __init__(self, k: int = 2, rewriter: Callable = _default_rewriter,
                 online_decay: bool = False, decay_window: int = 3,
                 epsilon: Optional[float] = None,
                 similarity: Optional[Callable] = None,
                 slot_merge: bool = True,
                 paraphrase_guard: bool = True,
                 slot_merge_threshold: float = 0.66,
                 paraphrase_threshold: float = 0.90):
        """
        k             : distinct independent episodes to trigger accommodation.
        online_decay  : if True, a stalled candidate (<k votes) is flushed to an
                        exception ONLINE once `decay_window` later episodes pass
                        without corroborating it, instead of only at finalize().
        decay_window  : episodes of no-corroboration after which a stalled
                        candidate decays into a protected exception.
        epsilon       : reconstruction tolerance for DISSOLVE. If set, a congruent
                        observation with pred_error <= epsilon is deemed already
                        reconstructable from the schema; its raw text is released
                        (Observation.forgettable=True, slot.forgotten += 1) and
                        ingest() returns DISSOLVE. None disables forgetting.
        similarity    : optional callable (a: str, b: str) -> float in [0,1]. When
                        provided it powers two guards: (i) SLOT CANONICALIZATION —
                        a would-be-new slot whose name is near an existing slot of
                        the same entity is merged into it; (ii) PARAPHRASE guard — a
                        candidate about to accommodate whose value is near the current
                        belief is treated as reinforcement (ASSIMILATE), not a change.
                        None disables both guards (pure structural behaviour).
        slot_merge_threshold : cosine >= this merges a new slot into an existing one.
        paraphrase_threshold : cosine >= this treats an accommodation as a paraphrase.
        """
        self.k = k
        self.rewriter = rewriter
        self.online_decay = online_decay
        self.decay_window = decay_window
        self.epsilon = epsilon
        self.similarity = similarity
        self.slot_merge = slot_merge
        self.paraphrase_guard = paraphrase_guard
        self.slot_merge_threshold = slot_merge_threshold
        self.paraphrase_threshold = paraphrase_threshold
        self._episode_order: dict = {}                   # episode_id -> monotonic idx
        self.entities: dict = {}                         # entity -> Schema

    def get_schema(self, entity: str) -> Schema:
        if entity not in self.entities:
            self.entities[entity] = Schema(entity=entity)
        return self.entities[entity]

    def _episode_idx(self, episode_id: str) -> int:
        """Monotonic order index for an episode_id (first time seen -> next int)."""
        if episode_id not in self._episode_order:
            self._episode_order[episode_id] = len(self._episode_order)
        return self._episode_order[episode_id]

    def _decay_sweep(self, slot: Slot, now_idx: int) -> list:
        """Online-decay: stalled candidates untouched for > decay_window episodes
        become protected exceptions immediately (not at finalize)."""
        protected = []
        for cid, cand in list(slot.candidates.items()):
            if 0 < len(cand.votes) < self.k and (now_idx - cand.last_episode_idx) > self.decay_window:
                for o in cand.observations:
                    slot.exceptions.append(o)
                    protected.append((slot.name, o, Action.PROTECT))
                del slot.candidates[cid]
        return protected

    @staticmethod
    def _slot_descriptor(name: str, value) -> str:
        """A short text signal for a slot: its name plus a representative value.
        The value carries most of the semantic signal (abstract names like
        'relaxation_method' and 'artwork' look far apart, but their values are both
        'painting')."""
        name = name.replace("_", " ")
        return f"{name}: {value}" if value else name

    def _canonical_slot_name(self, schema: "Schema", name: str, value) -> str:
        """(a) Slot canonicalization: if `name` is not an existing slot but is close
        (by similarity, comparing name+value descriptors) to one that already exists
        on this entity, return that existing slot's name so the observation lands
        there instead of minting a near-duplicate slot. No-op when similarity is
        disabled or the slot already exists."""
        if (self.similarity is None or not self.slot_merge
                or name in schema.slots or not schema.slots):
            return name
        incoming = self._slot_descriptor(name, value)
        best, best_sim = name, 0.0
        for existing, slot in schema.slots.items():
            ref = self._slot_descriptor(existing, slot.belief)
            sim = self.similarity(incoming, ref)
            if sim > best_sim:
                best, best_sim = existing, sim
        return best if best_sim >= self.slot_merge_threshold else name

    def ingest(self, obs: Observation) -> Action:
        """Route one observation and mutate the slot. Returns the action taken."""
        schema = self.get_schema(obs.entity)
        obs.slot = self._canonical_slot_name(schema, obs.slot, obs.value)
        slot = schema.get_slot(obs.slot)
        slot.ledger.append(obs)
        idx = self._episode_idx(obs.episode_id)

        # online decay: age out stalled candidates on this slot before routing.
        if self.online_decay:
            self._decay_sweep(slot, idx)

        # (0) first observation on an empty slot seeds the belief. There is nothing
        #     to conflict with yet, so a non-null candidate_id from the extractor is
        #     irrelevant here — a low-pred_error observation forms the initial belief.
        #     (A high-pred_error obs on an empty slot is degenerate; still seed it,
        #     since there is no prior belief for it to violate.)
        if slot.belief is None:
            slot.belief = obs.value
            slot.belief_t = obs.t
            if obs.candidate_id is not None:
                slot.won_lines.add(obs.candidate_id)   # the seed line counts as won
            return Action.ASSIMILATE

        # (1) congruent with current belief -> ASSIMILATE (or DISSOLVE if reconstructable)
        #     either explicitly marked (candidate_id None) or on the belief line.
        if obs.candidate_id is None or obs.value == slot.belief or obs.candidate_id in slot.won_lines:
            # reconstruction-gated forgetting: schema already predicts this obs.
            if self.epsilon is not None and obs.pred_error <= self.epsilon:
                obs.forgettable = True
                slot.forgotten += 1
                return Action.DISSOLVE
            return Action.ASSIMILATE

        # (2) violation -> open / extend a candidate, count DISTINCT episodes
        cand = slot.candidates.setdefault(
            obs.candidate_id, Candidate(candidate_id=obs.candidate_id))
        cand.votes.add(obs.episode_id)
        cand.observations.append(obs)
        cand.last_episode_idx = idx

        # (3) enough independent corroboration -> ACCOMMODATE
        if len(cand.votes) >= self.k:
            # (b) Paraphrase guard: a corroborated candidate whose value merely
            #     restates the current belief is reinforcement, not a real change.
            #     Reinforce (mark the line won, keep the belief) instead of
            #     superseding, so paraphrases don't manufacture a false evolution.
            if (self.similarity is not None and self.paraphrase_guard and slot.belief is not None
                    and self.similarity(obs.value, slot.belief) >= self.paraphrase_threshold):
                slot.won_lines.add(obs.candidate_id)
                del slot.candidates[obs.candidate_id]
                return Action.ASSIMILATE
            if slot.belief is not None:
                slot.superseded.append((slot.belief, obs.t))
            slot.belief = self.rewriter(slot.belief, cand)
            slot.belief_t = obs.t
            # the winning candidate is now the belief; record + clear it
            slot.won_lines.add(obs.candidate_id)
            del slot.candidates[obs.candidate_id]
            return Action.ACCOMMODATE

        # (4) violation still under threshold -> ACCUMULATE
        return Action.ACCUMULATE

    def finalize(self) -> list:
        """After the full stream: any candidate below k with no path to win is an
        exception. Each of its observations is kept verbatim in slot.exceptions.
        Returns the list of (entity, slot, Observation, Action.PROTECT) stamped,
        so PROTECT is an emitted action (at stream end) rather than implicit.
        """
        protected = []
        for schema in self.entities.values():
            for slot in schema.slots.values():
                for cid, cand in list(slot.candidates.items()):
                    if 0 < len(cand.votes) < self.k:
                        for o in cand.observations:
                            slot.exceptions.append(o)
                            protected.append((schema.entity, slot.name, o, Action.PROTECT))
                        del slot.candidates[cid]
        return protected
