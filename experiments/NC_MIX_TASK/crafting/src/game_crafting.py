"""
Crafting：九块石头上的正式实验状态机（三瓶药水由显式转化表或内置图生成）。

按键语义：
- Q：药水1 回路一正向 · E：同回路逆向 · A：药水2 回路二正向 · D：同回路逆向 · W：药水3 大环
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .config_io_crafting import TrialListData, TrialSpec
from .stone_space import display_name
from .recorder import RLDataRecorder
from .rules_io_crafting import RuleDataCrafting
from .validation_crafting import choose_reachable_targets_multi_starts


@dataclass(frozen=True)
class Action:
    npc: str
    label: str
    kind: str
    param: str
    next_state: str


class GameCrafting:
    def __init__(
        self,
        recorder: RLDataRecorder,
        rules: RuleDataCrafting,
        trial_data: TrialListData,
        *,
        practice_mode: bool = False,
        finite_trials: bool = False,
    ):
        self.recorder = recorder
        self.practice_mode = bool(practice_mode)
        self.finite_trials = bool(finite_trials)
        self.session_complete: bool = False
        self.map_id = rules.map_id
        self.rule_source = rules.source_path
        self.transition_map_path = rules.transition_map_path or ""
        self.potion1: Dict[str, str] = dict(rules.potion1)
        self.potion1_rev: Dict[str, str] = dict(rules.potion1_rev)
        self.potion2: Dict[str, str] = dict(rules.potion2)
        self.potion2_rev: Dict[str, str] = dict(rules.potion2_rev)
        self.potion3: Dict[str, str] = dict(rules.potion3)
        self.trials: List[TrialSpec] = trial_data.trials
        self.trial_source = trial_data.source_path

        self.trial_index = -1
        self.current_trial: Optional[TrialSpec] = None

        self.order_targets: List[str] = []
        self.order_index = 0
        self.step_count = 0
        self.key_step_in_order = 0

        self.active_raw_start_state_id: Optional[str] = None
        self.current_state_id: str = ""

        self.current_order_start_time = time.time()
        self.last_status_message = ""

        self.order_complete_overlay_pending: bool = False
        self._defer_start_next_trial: bool = False

        self.start_next_trial()

    def _build_trial_targets(
        self,
        trial: TrialSpec,
        rng: random.Random,
    ) -> Tuple[List[str], List[str]]:
        requested_targets = trial.targets or []
        min_distance = int(getattr(trial, "min_distance", 2))
        return choose_reachable_targets_multi_starts(
            requested_targets=requested_targets,
            raw_states=trial.raws,
            order_count=trial.order_count,
            potion1_fwd=self.potion1,
            potion1_rev=self.potion1_rev,
            potion2_fwd=self.potion2,
            potion2_rev=self.potion2_rev,
            potion3=self.potion3,
            rng=rng,
            min_distance=max(1, min_distance),
            strict_requested=trial.strict_order_targets,
        )

    def start_next_trial(self) -> bool:
        if not self.trials:
            return False

        self.trial_index += 1
        if self.trial_index >= len(self.trials):
            if self.finite_trials:
                self.session_complete = True
                self.current_trial = None
                self.order_targets = []
                self.active_raw_start_state_id = None
                self.current_state_id = ""
                self.order_complete_overlay_pending = False
                self._defer_start_next_trial = False
                return False
            self.trial_index = 0

        trial = self.trials[self.trial_index]
        rng = random.Random(trial.seed) if trial.seed is not None else random.Random()

        targets, messages = self._build_trial_targets(trial, rng)

        self.current_trial = trial
        self.order_targets = targets
        self.order_index = 0
        self.step_count = 0
        self.key_step_in_order = 0

        start = trial.raws[0]
        self.active_raw_start_state_id = start
        self.current_state_id = start

        self.current_order_start_time = time.time()
        self.last_status_message = messages[-1] if messages else f"已开始 {trial.trial_id}"

        self.order_complete_overlay_pending = False
        self._defer_start_next_trial = False

        self.recorder.start_episode()
        return True

    def clear_operation_slot(self) -> bool:
        if not self.current_trial:
            return False

        default_raw = self.current_trial.raws[0] if self.current_trial.raws else ""
        if not default_raw:
            return False

        self.active_raw_start_state_id = default_raw
        self.order_index = 0
        self.step_count = 0
        self.key_step_in_order = 0
        self.current_state_id = default_raw

        self.current_order_start_time = time.time()
        self.last_status_message = "已重置为本单起始石块"
        self._log_behavior_row(
            key_symbol="R",
            outcome="reset_operation_slot",
            executed=False,
            reaction_time_ms=0.0,
            prev_state=default_raw,
            next_state=default_raw,
            action_kind="",
            action_param="",
            action_detail="",
            order_target=self.current_target(),
            order_index_1based=self.order_index + 1,
            order_completed=False,
            trial_done=False,
            reward=0.0,
            bump_key_step=False,
        )
        return True

    def can_execute(self) -> bool:
        if self.session_complete:
            return False
        return self.current_trial is not None and self.active_raw_start_state_id is not None

    def current_target(self) -> str:
        if not self.order_targets:
            return self.current_state_id
        idx = min(self.order_index, len(self.order_targets) - 1)
        return self.order_targets[idx]

    def remaining_orders(self) -> int:
        return max(0, len(self.order_targets) - self.order_index)

    @property
    def completes_trial_after_order_overlay(self) -> bool:
        """当前「订单完成」覆层对应的是 trial 内最后一单（关闭覆层后将进入下一 trial）。"""
        return self._defer_start_next_trial

    def is_trial_done(self) -> bool:
        return self.order_index >= len(self.order_targets)

    def _behavior_common(self) -> Dict[str, Any]:
        tid = self.current_trial.trial_id if self.current_trial else ""
        if self.current_trial is not None:
            seq = self.trial_index + 1
        elif self.session_complete and self.trials:
            seq = len(self.trials)
        else:
            seq = 0
        out: Dict[str, Any] = {
            "Trial_Block_ID": tid,
            "Trial_Block_Sequence": seq,
            "Order_In_Block": self.order_index + 1,
            "Orders_In_Block_Total": len(self.order_targets),
            "Start_State": self.active_raw_start_state_id or "",
            "Map_ID": self.map_id,
            "Transition_Map_Path": self.transition_map_path,
            "Rules_Source": self.rule_source,
            "Trial_Source": self.trial_source,
        }
        m = self.current_trial.schedule_meta if self.current_trial and self.current_trial.schedule_meta else None
        if m:
            out["Proposal5_Session"] = m.get("session", "")
            out["Proposal5_Block_Index"] = m.get("block_index", "")
            out["Proposal5_Pair_ID"] = m.get("pair_id", "")
            out["Proposal5_Category"] = m.get("category", "")
            out["Proposal5_Nav_Start"] = m.get("nav_start", "")
            out["Proposal5_Nav_Goal"] = m.get("nav_goal", "")
            out["Proposal5_d_grid"] = m.get("d_grid", "")
            out["Proposal5_d_loop"] = m.get("d_loop", "")
        return out

    def _shortest_path_len_to_target(self, state: str, target: str) -> Optional[int]:
        """按键前状态下到当前订单目标的最短步数（与可操作药水邻接一致）；不可达为 None。"""
        if not target or not state:
            return None
        if state == target:
            return 0
        from .validation_crafting import bfs_distances_player_moves

        dm = bfs_distances_player_moves(
            state,
            self.potion1,
            self.potion1_rev,
            self.potion2,
            self.potion2_rev,
            self.potion3,
        )
        d = dm.get(target)
        return d if d is not None else None

    def log_invalid_keypress(self, key_symbol: str, reason: str) -> None:
        """无效药水键：无对应动作或执行失败。reason 如 invalid_no_action / invalid_execute_failed。"""
        if not self.current_trial:
            return
        rt_ms = (time.time() - self.current_order_start_time) * 1000.0
        self._log_behavior_row(
            key_symbol=key_symbol,
            outcome=reason,
            executed=False,
            reaction_time_ms=rt_ms,
            prev_state=self.current_state_id,
            next_state=self.current_state_id,
            action_kind="",
            action_param="",
            action_detail="",
            order_target=self.current_target(),
            order_index_1based=self.order_index + 1,
            order_completed=False,
            trial_done=False,
            reward=0.0,
            bump_key_step=True,
        )

    def _verify_action(self, cur: str, action: Action) -> bool:
        if action.kind == "ring1_step":
            if action.param == "+1":
                nxt = self.potion1.get(cur)
            elif action.param == "-1":
                nxt = self.potion1_rev.get(cur)
            else:
                return False
            return nxt is not None and action.next_state == nxt
        if action.kind == "ring2_step":
            if action.param == "+1":
                nxt = self.potion2.get(cur)
            elif action.param == "-1":
                nxt = self.potion2_rev.get(cur)
            else:
                return False
            return nxt is not None and action.next_state == nxt
        if action.kind == "w_cycle":
            nxt = self.potion3.get(cur)
            return nxt is not None and action.next_state == nxt
        return False

    def get_available_actions(self) -> List[Action]:
        if self.session_complete or not self.current_trial:
            return []
        cur = self.current_state_id
        actions: List[Action] = []

        n1 = self.potion1.get(cur)
        if n1 is not None:
            actions.append(
                Action("炼金台", "魔法药水1（Q·回路一正向）", "ring1_step", "+1", n1)
            )
        n1b = self.potion1_rev.get(cur)
        if n1b is not None:
            actions.append(
                Action("炼金台", "魔法药水1（E·回路一逆向）", "ring1_step", "-1", n1b)
            )

        n2 = self.potion2.get(cur)
        if n2 is not None:
            actions.append(
                Action("炼金台", "魔法药水2（A·回路二正向）", "ring2_step", "+1", n2)
            )
        n2b = self.potion2_rev.get(cur)
        if n2b is not None:
            actions.append(
                Action("炼金台", "魔法药水2（D·回路二逆向）", "ring2_step", "-1", n2b)
            )

        if self.can_execute():
            n3 = self.potion3.get(cur)
            if n3 is not None:
                actions.append(
                    Action("炼金台", "魔法药水3（九石大环）", "w_cycle", "", n3)
                )

        return actions

    def execute_action(self, action: Action, *, source_key: str = "") -> bool:
        if not self.can_execute():
            return False

        if not self._verify_action(self.current_state_id, action):
            return False

        if action.next_state == self.current_state_id:
            return False

        prev = self.current_state_id
        rt_ms = (time.time() - self.current_order_start_time) * 1000.0

        if self.practice_mode:
            self.current_state_id = action.next_state
            self.step_count += 1
            self.current_order_start_time = time.time()
            target = self.current_target()
            self._log_step(
                action=action,
                prev_state=prev,
                order_target=target,
                order_completed=False,
                trial_done=False,
                completed_before=self.order_index,
                reaction_time_ms=rt_ms,
                source_key=source_key or "?",
            )
            self.last_status_message = f"{action.label} → {display_name(self.current_state_id)}"
            return True

        target = self.current_target()
        completed_before = self.order_index

        self.current_state_id = action.next_state
        self.step_count += 1

        order_completed = self.current_state_id == target
        if order_completed:
            self.order_index += 1
            if not self.is_trial_done():
                assert self.active_raw_start_state_id is not None
                self.current_state_id = self.active_raw_start_state_id
                self.current_order_start_time = time.time()
                self.key_step_in_order = 0

        trial_done = self.is_trial_done()

        self._log_step(
            action=action,
            prev_state=prev,
            order_target=target,
            order_completed=order_completed,
            trial_done=trial_done,
            completed_before=completed_before,
            reaction_time_ms=rt_ms,
            source_key=source_key or "?",
        )

        if order_completed:
            # 直接进入下一 trial，不弹出订单完成弹窗
            self.order_complete_overlay_pending = False
            self.last_status_message = "订单完成"
            if trial_done:
                self.start_next_trial()
        else:
            self.last_status_message = f"{action.label} → {display_name(self.current_state_id)}"
        return True

    def dismiss_order_complete_overlay(self) -> None:
        if not self.order_complete_overlay_pending:
            return
        self.order_complete_overlay_pending = False
        if self._defer_start_next_trial:
            self._defer_start_next_trial = False
            self.start_next_trial()

    def _log_step(
        self,
        action: Action,
        prev_state: str,
        order_target: str,
        order_completed: bool,
        trial_done: bool,
        completed_before: int,
        reaction_time_ms: float,
        source_key: str,
    ) -> None:
        self._log_behavior_row(
            key_symbol=source_key,
            outcome="executed",
            executed=True,
            reaction_time_ms=reaction_time_ms,
            prev_state=prev_state,
            next_state=self.current_state_id,
            action_kind=action.kind,
            action_param=action.param,
            action_detail=action.label,
            order_target=order_target,
            order_index_1based=completed_before + 1,
            order_completed=order_completed,
            trial_done=trial_done,
            reward=1.0 if order_completed else 0.0,
            bump_key_step=True,
            npc=action.npc,
        )

    def _log_behavior_row(
        self,
        *,
        key_symbol: str,
        outcome: str,
        executed: bool,
        reaction_time_ms: float,
        prev_state: str,
        next_state: str,
        action_kind: str,
        action_param: str,
        action_detail: str,
        order_target: str,
        order_index_1based: int,
        order_completed: bool,
        trial_done: bool,
        reward: float,
        bump_key_step: bool,
        npc: str = "",
    ) -> None:
        if bump_key_step:
            self.key_step_in_order += 1
        common = self._behavior_common()
        extra: Dict[str, Any] = {}
        if npc:
            extra["NPC"] = npc
        shortest = self._shortest_path_len_to_target(prev_state, order_target)
        proposal_kw = {
            k: v
            for k, v in common.items()
            if k.startswith("Proposal5_")
        }
        self.recorder.log_action(
            episode=self.trial_index + 1,
            step=self.step_count,
            map_type=f"crafting_{self.map_id}",
            current_room_id=0,
            pos_x=0,
            pos_y=0,
            backpack=[next_state],
            action_name=action_kind or "key_press",
            action_detail=action_detail or outcome,
            reward=reward,
            is_valid=executed,
            game_over=trial_done,
            Trial_ID=common["Trial_Block_ID"] or "unknown",
            Trial_Source=common["Trial_Source"],
            Rules_Source=common["Rules_Source"],
            Map_ID=common["Map_ID"],
            Start_State=common["Start_State"],
            Prev_State=prev_state,
            Current_State=next_state,
            Order_Target=order_target,
            Order_Index=order_index_1based,
            Order_Completed=int(order_completed),
            Trial_Completed=int(trial_done),
            Remaining_Orders=self.remaining_orders(),
            Action_Kind=action_kind,
            Action_Param=action_param,
            Reaction_Time_ms=round(reaction_time_ms, 2),
            Key_Symbol=key_symbol,
            Key_Step_In_Order=self.key_step_in_order,
            Order_In_Block=order_index_1based,
            Trial_Block_ID=common["Trial_Block_ID"],
            Trial_Block_Sequence=common["Trial_Block_Sequence"],
            Orders_In_Block_Total=common["Orders_In_Block_Total"],
            Transition_Map_Path=common["Transition_Map_Path"],
            Outcome=outcome,
            Executed=int(executed),
            Move_Step_After=self.step_count,
            Shortest_Path_Len_To_Target=shortest,
            **proposal_kw,
            **extra,
        )
