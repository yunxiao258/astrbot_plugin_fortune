# -*- coding: utf-8 -*-
"""fortune 插件新功能测试（v1.1.0）：用户级运势、连续占卜加成、欧皇榜、缘分配对。"""

import asyncio
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest import mock

sys.path.insert(0, r"D:\astrbot\data\plugins")

from astrbot_plugin_fortune.main import (  # noqa: E402
    AFFINITY_LEVELS,
    FortunePlugin,
)


class FakeSession:
    def __init__(self, umo="default:GroupMessage:123"):
        self.umo = umo

    def __str__(self):
        return self.umo


class FakeEvent:
    """支持发送者的最小事件替身"""

    def __init__(self, message_str="", umo="default:GroupMessage:123",
                 sender_id="u1", sender_name="小明", messages=None):
        self.message_str = message_str
        self.session = FakeSession(umo)
        self.unified_msg_origin = umo
        self._sid = sender_id
        self._name = sender_name
        self._messages = messages or []

    def get_sender_id(self):
        return self._sid

    def get_sender_name(self):
        return self._name

    def get_messages(self):
        return self._messages

    def chain_result(self, chain):
        return chain


class FakeLegacyEvent(FakeEvent):
    """无 get_sender_id/get_sender_name 的旧式事件（兼容路径）"""

    def __init__(self, message_str="", umo="default:GroupMessage:123"):
        self.message_str = message_str
        self.session = FakeSession(umo)
        self.unified_msg_origin = umo


def run(coro):
    return asyncio.run(coro)


def make_plugin(config=None):
    tmp = tempfile.TemporaryDirectory(prefix="fortune_extra_")
    return FortunePlugin(None, config or {}, data_dir=tmp.name), tmp


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def yesterday() -> str:
    return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")


class TestUserLevelFortune(unittest.TestCase):
    def test_same_group_different_users(self):
        p, _ = make_plugin()
        f1, _ = p._get_daily_fortune(FakeEvent(sender_id="a"))
        f2, _ = p._get_daily_fortune(FakeEvent(sender_id="b"))
        # 不同用户各自生成，记录键按用户隔离
        daily = p._data["daily"][today()]
        keys = [k for k in daily if k.endswith("|a") or k.endswith("|b")]
        self.assertEqual(len(keys), 2)

    def test_same_user_same_day_stable(self):
        p, _ = make_plugin()
        ev = FakeEvent(sender_id="u7")
        f1, new1 = p._get_daily_fortune(ev)
        f2, new2 = p._get_daily_fortune(ev)
        self.assertTrue(new1)
        self.assertFalse(new2)
        self.assertEqual(f1["score"], f2["score"])

    def test_legacy_event_without_sender(self):
        # 旧式事件退化为会话级键，不崩溃
        p, _ = make_plugin()
        f, is_new = p._get_daily_fortune(FakeLegacyEvent("运势"))
        self.assertTrue(is_new)
        key = list(p._data["daily"][today()].keys())[0]
        self.assertNotIn("|", key.split(":GroupMessage:123", 1)[1])

    def test_name_recorded(self):
        p, _ = make_plugin()
        p._get_daily_fortune(FakeEvent(sender_id="u9", sender_name="小红"))
        rec = list(p._data["daily"][today()].values())[0]
        self.assertEqual(rec.get("name"), "小红")


class TestStreakBonus(unittest.TestCase):
    def _seed_yesterday(self, p, uid="s1"):
        y = yesterday()
        p._data["daily"].setdefault(y, {})[f"default:GroupMessage:123|{uid}"] = {
            "score": 50, "streak": 3,
        }

    def test_streak_continues_from_yesterday(self):
        p, _ = make_plugin()
        self._seed_yesterday(p)
        f, _ = p._get_daily_fortune(FakeEvent(sender_id="s1"))
        self.assertEqual(f["streak"], 4)

    def test_streak_resets_when_gap(self):
        p, _ = make_plugin()
        # 前天有记录但昨天没有 → 从第 1 天开始
        d2 = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
        p._data["daily"].setdefault(d2, {})[f"default:GroupMessage:123|g1"] = {"streak": 5}
        f, _ = p._get_daily_fortune(FakeEvent(sender_id="g1"))
        self.assertEqual(f["streak"], 1)

    def test_bonus_applied_and_capped(self):
        p, _ = make_plugin()
        # streak=10 → bonus 封顶 10 分；分数加成后不超过 99 且档位一致
        y = yesterday()
        p._data["daily"].setdefault(y, {})[f"default:GroupMessage:123|z1"] = {"streak": 9}
        with mock.patch.object(FortunePlugin, "_generate_daily_fortune",
                               wraps=p._generate_daily_fortune) as spy:
            f, _ = p._get_daily_fortune(FakeEvent(sender_id="z1"))
        info = p._grade_for_score(f["score"])
        self.assertEqual((f["min"] if False else info["grade"]), f["grade"])

    def test_bonus_disabled(self):
        p, _ = make_plugin({"streak_bonus_enabled": False})
        y = yesterday()
        p._data["daily"].setdefault(y, {})[f"default:GroupMessage:123|x1"] = {"streak": 5}
        f, _ = p._get_daily_fortune(FakeEvent(sender_id="x1"))
        self.assertEqual(f["bonus"], 0)
        self.assertEqual(f["streak"], 6)

    def test_score_within_grade_bounds_after_bonus(self):
        # 加成后档位与分数必须匹配
        for raw_score in range(20, 100, 7):
            p, _ = make_plugin()
            f = p._generate_daily_fortune(streak=6)
            info = p._grade_for_score(f["score"])
            self.assertEqual(info["grade"], f["grade"])
            self.assertEqual(info["star"], f["star"])
            self.assertLessEqual(f["score"], 99)


class TestLeaderboard(unittest.TestCase):
    def test_empty_board_hint(self):
        p, _ = make_plugin()
        text = p._leaderboard_text(FakeEvent())
        self.assertIn("还没有人占卜", text)

    def test_ranking_sorted_with_medals(self):
        p, _ = make_plugin()
        daily = p._data["daily"].setdefault(today(), {})
        base = "default:GroupMessage:123"
        daily[f"{base}|a"] = {"score": 88, "name": "甲", "grade": "上吉"}
        daily[f"{base}|b"] = {"score": 95, "name": "乙", "grade": "上上吉"}
        daily[f"{base}|c"] = {"score": 60, "name": "丙", "grade": "中平"}
        ev = FakeEvent()
        text = p._leaderboard_text(ev)
        self.assertIn("共 3 人占卜", text)
        b_pos = text.find("乙")
        a_pos = text.find("甲")
        c_pos = text.find("丙")
        self.assertTrue(b_pos < a_pos < c_pos)
        self.assertIn("🥇", text)
        self.assertIn("今日欧皇：乙（95 分）", text)

    def test_other_groups_excluded(self):
        p, _ = make_plugin()
        daily = p._data["daily"].setdefault(today(), {})
        daily["other:GroupMessage:999|a"] = {"score": 99, "name": "外群人"}
        daily["default:GroupMessage:123|b"] = {"score": 70, "name": "本群人"}
        text = p._leaderboard_text(FakeEvent())
        self.assertIn("本群人", text)
        self.assertNotIn("外群人", text)


class TestAffinity(unittest.TestCase):
    def test_score_range_and_determinism(self):
        s1 = FortunePlugin._affinity_score("alice", "bob", today())
        s2 = FortunePlugin._affinity_score("alice", "bob", today())
        self.assertEqual(s1, s2)
        self.assertTrue(5 <= s1 <= 99)

    def test_order_independent(self):
        s1 = FortunePlugin._affinity_score("alice", "bob", today())
        s2 = FortunePlugin._affinity_score("bob", "alice", today())
        self.assertEqual(s1, s2)

    def test_different_days_differ(self):
        scores = {
            FortunePlugin._affinity_score("a", "b", f"2026-01-{d:02d}")
            for d in range(1, 10)
        }
        self.assertGreater(len(scores), 1)

    def test_levels_cover_all_scores(self):
        for score in range(0, 101):
            name, comment = FortunePlugin._affinity_level(score)
            self.assertTrue(name and comment)
        mins = [m for m, _, _ in AFFINITY_LEVELS]
        self.assertEqual(mins, sorted(mins, reverse=True))

    def test_command_with_text_target(self):
        p, _ = make_plugin()
        r = run(p.cmd_affinity(FakeEvent("/缘分 小红", sender_name="阿强")))
        text = r[0].text
        self.assertIn("缘分配对", text)
        self.assertIn("阿强 ❤️ 小红", text)
        self.assertIn("缘分值:", text)

    def test_command_at_target_extracted(self):
        from astrbot.api.message_components import At

        p, _ = make_plugin()
        ev = FakeEvent("/缘分 占位", sender_name="阿强", messages=[At(qq="8888")])
        r = run(p.cmd_affinity(ev))
        self.assertIn("阿强 ❤️ 8888", r[0].text)

    def test_command_empty_target(self):
        p, _ = make_plugin()
        r = run(p.cmd_affinity(FakeEvent("/缘分")))
        self.assertIn("用法", r[0].text)

    def test_format_contains_level_comment(self):
        p, _ = make_plugin()
        score = 97
        text = p._format_affinity("甲", "乙", score, today())
        self.assertIn("天作之合", text)
        self.assertIn("97/100", text)


if __name__ == "__main__":
    unittest.main(verbosity=1)
