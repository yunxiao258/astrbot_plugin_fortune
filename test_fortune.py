# -*- coding: utf-8 -*-
"""astrbot_plugin_fortune 单元测试：内容库 / 参数解析 / 今日运势 / 星座 / 生肖 / 抽签 / 配置防御"""
import asyncio
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from astrbot_plugin_fortune.main import (  # noqa: E402
    ADVICES,
    GRADE_INFO,
    JI_LIST,
    LOTS,
    LUCKY_COLORS,
    ONE_LINERS,
    SIGNS,
    SIGN_ALIASES,
    YI_LIST,
    ZODIACS,
    FortunePlugin,
)


class FakeSession:
    """最小会话替身：仅提供 str() 表示"""
    def __init__(self, umo="default:GroupMessage:123"):
        self.umo = umo

    def __str__(self):
        return self.umo


class FakeEvent:
    """最小事件替身：仅支持 message_str 与 session"""
    def __init__(self, message_str="", umo="default:GroupMessage:123"):
        self.message_str = message_str
        self.session = FakeSession(umo)

    def chain_result(self, chain):
        return chain


def run(coro):
    """运行异步协程并返回结果"""
    return asyncio.run(coro)


class FortuneTestCase(unittest.TestCase):
    """基类：每个测试注入独立临时数据目录，避免污染真实 plugin_data"""

    def _make(self, config=None):
        tmp = tempfile.TemporaryDirectory(prefix="fortune_test_")
        self.addCleanup(tmp.cleanup)
        return FortunePlugin(None, config or {}, data_dir=tmp.name)


class TestContentLibraries(unittest.TestCase):
    """内容库规模与结构检查"""

    def test_color_yi_ji_at_least_8(self):
        # 幸运色/宜/忌 各不少于 8 种
        self.assertGreaterEqual(len(LUCKY_COLORS), 8)
        self.assertGreaterEqual(len(YI_LIST), 8)
        self.assertGreaterEqual(len(JI_LIST), 8)

    def test_combined_templates_at_least_60(self):
        # 每日运势内容库组件总数 >= 60（评语 + 幸运色 + 宜 + 忌 + 一句话 + 忠告）
        total = (
            sum(len(g["comments"]) for g in GRADE_INFO)
            + len(LUCKY_COLORS)
            + len(YI_LIST)
            + len(JI_LIST)
            + len(ONE_LINERS)
            + len(ADVICES)
        )
        self.assertGreaterEqual(total, 60)

    def test_signs_count_12(self):
        self.assertEqual(len(SIGNS), 12)
        # 别名最终都解析到 12 个星座之一
        resolved = {FortunePlugin.resolve_sign(k) for k in SIGN_ALIASES}
        self.assertEqual(resolved, set(SIGNS.keys()))
        self.assertEqual(len(resolved), 12)

    def test_zodiacs_count_12(self):
        self.assertEqual(len(ZODIACS), 12)

    def test_lots_count_and_grades(self):
        # 签文库至少 30 签，覆盖 上上/上/中/下 四档
        self.assertGreaterEqual(len(LOTS), 30)
        grades = {lot["grade"] for lot in LOTS}
        self.assertTrue({"上上", "上", "中", "下"} <= grades)

    def test_lots_all_have_poem_and_explain(self):
        for lot in LOTS:
            self.assertTrue(lot["poem"], f"第 {lot['no']} 签缺少签诗")
            self.assertTrue(lot["explain"], f"第 {lot['no']} 签缺少解签文")


class TestParseArgs(unittest.TestCase):
    """指令参数解析：兼容带 /、／ 或不带斜杠的前缀"""

    def test_no_prefix(self):
        self.assertEqual(FortunePlugin.parse_cmd_args("运势", "运势"), "")

    def test_slash_prefix(self):
        self.assertEqual(FortunePlugin.parse_cmd_args("/运势", "运势"), "")

    def test_fullwidth_slash_prefix(self):
        self.assertEqual(FortunePlugin.parse_cmd_args("／星座 双鱼", "星座"), "双鱼")

    def test_slash_with_args(self):
        self.assertEqual(FortunePlugin.parse_cmd_args("/星座 双鱼座", "星座"), "双鱼座")

    def test_extra_spaces(self):
        self.assertEqual(FortunePlugin.parse_cmd_args("  /生肖   牛  ", "生肖"), "牛")

    def test_not_match(self):
        # 指令不匹配时返回空串
        self.assertEqual(FortunePlugin.parse_cmd_args("抽签 今日", "运势"), "")

    def test_empty_text(self):
        self.assertEqual(FortunePlugin.parse_cmd_args("", "运势"), "")
        self.assertEqual(FortunePlugin.parse_cmd_args(None, "运势"), "")


class TestDailyFortune(FortuneTestCase):
    """今日运势：当日稳定 / 按会话记录 / 同日去重 / 持久化"""

    def test_daily_content_fields(self):
        p = self._make()
        result = run(p.cmd_daily(FakeEvent("/运势")))
        text = result[0].text
        self.assertIn("总评", text)
        self.assertIn("幸运色", text)
        self.assertIn("幸运数字", text)
        self.assertIn("宜:", text)
        self.assertIn("忌:", text)

    @staticmethod
    def _strip_note(text):
        """去掉"已占卜过"提示行，仅比较运势主体内容"""
        return "\n".join(line for line in text.splitlines() if "已占卜过" not in line)

    def test_daily_same_day_stable(self):
        # 同会话同日重复查询：主体内容一致；重复查询附加"已占卜过"提示
        p = self._make()
        r1 = run(p.cmd_daily(FakeEvent("/运势")))
        r2 = run(p.cmd_daily(FakeEvent("/运势")))
        r3 = run(p.cmd_daily(FakeEvent("运势")))
        self.assertEqual(r2[0].text, r3[0].text)
        self.assertEqual(self._strip_note(r1[0].text), self._strip_note(r2[0].text))
        self.assertIn("已占卜过", r2[0].text)
        self.assertNotIn("已占卜过", r1[0].text)

    def test_daily_second_call_marks_already_checked(self):
        p = self._make()
        r1 = run(p.cmd_daily(FakeEvent("/运势")))
        self.assertNotIn("已占卜过", r1[0].text)
        r2 = run(p.cmd_daily(FakeEvent("/运势")))
        self.assertIn("已占卜过", r2[0].text)

    def test_daily_recorded_per_session(self):
        # 跨会话按会话独立记录
        p = self._make()
        ev1 = FakeEvent("/运势", umo="default:GroupMessage:111")
        ev2 = FakeEvent("/运势", umo="default:GroupMessage:222")
        run(p.cmd_daily(ev1))
        run(p.cmd_daily(ev2))
        today = datetime.now().strftime("%Y-%m-%d")
        daily = p._data["daily"][today]
        self.assertIn("default:GroupMessage:111", daily)
        self.assertIn("default:GroupMessage:222", daily)
        # 各自去重：再次查询不改变对方记录
        r1b = run(p.cmd_daily(ev1))
        self.assertIn("已占卜过", r1b[0].text)
        self.assertEqual(
            daily["default:GroupMessage:222"],
            p._data["daily"][today]["default:GroupMessage:222"],
        )

    def test_daily_persists_across_instances(self):
        # 持久化：重新实例化（模拟重启）后同日同会话结果不变
        with tempfile.TemporaryDirectory(prefix="fortune_daily_persist_") as tmp:
            p1 = FortunePlugin(None, {}, data_dir=tmp)
            run(p1.cmd_daily(FakeEvent("/运势")))
            r1 = run(p1.cmd_daily(FakeEvent("/运势")))  # 第二次：附加提示行
            p2 = FortunePlugin(None, {}, data_dir=tmp)
            r2 = run(p2.cmd_daily(FakeEvent("/运势")))
            self.assertEqual(r1[0].text, r2[0].text)
            self.assertIn("已占卜过", r2[0].text)
            self.assertTrue(os.path.exists(os.path.join(tmp, "fortune_data.json")))

    def test_daily_no_persistence(self):
        # 关闭持久化：不落盘
        with tempfile.TemporaryDirectory(prefix="fortune_daily_nopersist_") as tmp:
            p = FortunePlugin(None, {"enable_persistence": False}, data_dir=tmp)
            run(p.cmd_daily(FakeEvent("/运势")))
            self.assertFalse(os.path.exists(os.path.join(tmp, "fortune_data.json")))


class TestSignFortune(FortuneTestCase):
    """星座：别名解析 / 同日一致 / 非法输入容错"""

    def test_alias_resolution(self):
        self.assertEqual(FortunePlugin.resolve_sign("双鱼"), "双鱼座")
        self.assertEqual(FortunePlugin.resolve_sign("双鱼座"), "双鱼座")
        self.assertEqual(FortunePlugin.resolve_sign("水瓶"), "水瓶座")
        self.assertEqual(FortunePlugin.resolve_sign("天平"), "天秤座")
        self.assertEqual(FortunePlugin.resolve_sign("摩羯座"), "摩羯座")
        self.assertEqual(FortunePlugin.resolve_sign("山羊"), "摩羯座")

    def test_unknown_sign(self):
        self.assertEqual(FortunePlugin.resolve_sign("宇宙"), "")
        self.assertEqual(FortunePlugin.resolve_sign(""), "")

    def test_empty_sign_prompt(self):
        p = self._make()
        result = run(p.cmd_sign(FakeEvent("/星座")))
        self.assertIn("用法", result[0].text)

    def test_unknown_sign_prompt(self):
        p = self._make()
        result = run(p.cmd_sign(FakeEvent("/星座 宇宙座")))
        self.assertIn("可用星座", result[0].text)

    def test_sign_same_day_stable_with_alias(self):
        # 同日同星座结果一致（含别名 / 斜杠差异）
        p = self._make()
        r1 = run(p.cmd_sign(FakeEvent("/星座 双鱼")))
        r2 = run(p.cmd_sign(FakeEvent("／星座 双鱼座")))
        r3 = run(p.cmd_sign(FakeEvent("/星座 双鱼")))
        self.assertEqual(r1[0].text, r2[0].text)
        self.assertEqual(r1[0].text, r3[0].text)
        self.assertIn("双鱼座", r1[0].text)
        self.assertIn("综合指数", r1[0].text)

    def test_all_signs_work(self):
        p = self._make()
        for alias in ["白羊", "金牛", "双子", "巨蟹", "狮子", "处女",
                      "天秤", "天蝎", "射手", "摩羯", "水瓶", "双鱼"]:
            result = run(p.cmd_sign(FakeEvent(f"/星座 {alias}")))
            self.assertNotIn("用法", result[0].text, f"星座 {alias} 解析失败")


class TestZodiacFortune(FortuneTestCase):
    """生肖：解析 / 同日一致 / 非法输入容错"""

    def test_zodiac_resolution(self):
        self.assertEqual(FortunePlugin.resolve_zodiac("牛"), "牛")
        self.assertEqual(FortunePlugin.resolve_zodiac("属牛"), "牛")
        self.assertEqual(FortunePlugin.resolve_zodiac("生肖牛"), "牛")
        self.assertEqual(FortunePlugin.resolve_zodiac("龙"), "龙")
        self.assertEqual(FortunePlugin.resolve_zodiac("凤凰"), "")

    def test_empty_zodiac_prompt(self):
        p = self._make()
        result = run(p.cmd_zodiac(FakeEvent("/生肖")))
        self.assertIn("用法", result[0].text)

    def test_unknown_zodiac_prompt(self):
        p = self._make()
        result = run(p.cmd_zodiac(FakeEvent("/生肖 恐龙")))
        self.assertIn("可用生肖", result[0].text)

    def test_zodiac_same_day_stable(self):
        p = self._make()
        r1 = run(p.cmd_zodiac(FakeEvent("/生肖 牛")))
        r2 = run(p.cmd_zodiac(FakeEvent("/生肖 属牛")))
        r3 = run(p.cmd_zodiac(FakeEvent("/生肖 牛")))
        self.assertEqual(r1[0].text, r2[0].text)
        self.assertEqual(r1[0].text, r3[0].text)
        self.assertIn("生肖牛", r1[0].text)

    def test_all_zodiacs_work(self):
        p = self._make()
        for z in ["鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"]:
            result = run(p.cmd_zodiac(FakeEvent(f"/生肖 {z}")))
            self.assertNotIn("用法", result[0].text, f"生肖 {z} 解析失败")


class TestLotFortune(FortuneTestCase):
    """抽签：同题同日一致 / 解签输出 / 非法输入容错"""

    def test_lot_same_question_same_day_stable(self):
        p = self._make()
        r1 = run(p.cmd_lot(FakeEvent("/抽签 今天适合表白吗")))
        r2 = run(p.cmd_lot(FakeEvent("/抽签 今天适合表白吗")))
        r3 = run(p.cmd_lot(FakeEvent("抽签 今天适合表白吗")))
        self.assertEqual(r1[0].text, r2[0].text)
        self.assertEqual(r1[0].text, r3[0].text)

    def test_lot_contains_poem_and_explain(self):
        p = self._make()
        result = run(p.cmd_lot(FakeEvent("/抽签 事业运势如何")))
        text = result[0].text
        self.assertIn("签诗", text)
        self.assertIn("解签", text)
        self.assertIn("签级", text)

    def test_lot_draw_returns_valid_lot(self):
        lot = FortunePlugin.draw_lot("今天适合表白吗", "2026-08-15")
        self.assertIn(lot, LOTS)
        self.assertIn(lot["grade"], ("上上", "上", "中", "下"))

    def test_empty_question_prompt(self):
        p = self._make()
        result = run(p.cmd_lot(FakeEvent("/抽签")))
        self.assertIn("用法", result[0].text)


class TestHelp(FortuneTestCase):
    """帮助列表"""

    def test_help_lists_all_commands(self):
        p = self._make()
        result = run(p.cmd_help(FakeEvent("/占卜")))
        text = result[0].text
        self.assertIn("/运势", text)
        self.assertIn("/星座", text)
        self.assertIn("/生肖", text)
        self.assertIn("/抽签", text)
        self.assertIn("/占卜", text)


class TestConfigDefense(FortuneTestCase):
    """配置脏值防御：非法 int/bool 回退默认值"""

    def test_dirty_int_values(self):
        p = self._make({"lucky_number_max": "abc", "max_daily_records": None, "keep_days": "3.5"})
        self.assertEqual(p._int_cfg("lucky_number_max", 99), 99)
        self.assertEqual(p._int_cfg("max_daily_records", 1000), 1000)
        self.assertEqual(p._int_cfg("keep_days", 7), 7)

    def test_dirty_int_still_works_for_valid(self):
        p = self._make({"lucky_number_max": "50"})
        self.assertEqual(p._int_cfg("lucky_number_max", 99), 50)

    def test_dirty_bool_values(self):
        p = self._make({})
        self.assertTrue(p._bool_cfg("enable_persistence", True))
        p2 = self._make({"enable_persistence": "no"})
        self.assertFalse(p2._bool_cfg("enable_persistence", True))
        p3 = self._make({"enable_persistence": 0})
        self.assertFalse(p3._bool_cfg("enable_persistence", True))
        p4 = self._make({"enable_persistence": "maybe"})
        # 不可识别的字符串回退默认值
        self.assertTrue(p4._bool_cfg("enable_persistence", True))
        self.assertFalse(p4._bool_cfg("enable_persistence", False))

    def test_dirty_config_does_not_crash_daily(self):
        # 脏配置下今日运势仍可正常工作
        p = self._make({
            "lucky_number_max": "oops",
            "max_daily_records": "oops",
            "keep_days": "oops",
            "enable_persistence": "oops",
        })
        result = run(p.cmd_daily(FakeEvent("/运势")))
        self.assertIn("幸运数字", result[0].text)


class TestPersistenceData(FortuneTestCase):
    """持久化数据文件结构"""

    def test_data_file_structure(self):
        with tempfile.TemporaryDirectory(prefix="fortune_structure_") as tmp:
            p = FortunePlugin(None, {}, data_dir=tmp)
            run(p.cmd_daily(FakeEvent("/运势", umo="default:GroupMessage:555")))
            path = os.path.join(tmp, "fortune_data.json")
            self.assertTrue(os.path.exists(path))
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.assertIn("daily", data)
            today = datetime.now().strftime("%Y-%m-%d")
            fortune = data["daily"][today]["default:GroupMessage:555"]
            for field in ("score", "grade", "color", "number", "yi", "ji", "line"):
                self.assertIn(field, fortune)

    def test_corrupt_data_reset(self):
        # 损坏的数据文件不导致插件崩溃（结构校验重置）
        with tempfile.TemporaryDirectory(prefix="fortune_corrupt_") as tmp:
            with open(os.path.join(tmp, "fortune_data.json"), "w", encoding="utf-8") as f:
                f.write("not a json {{{")
            p = FortunePlugin(None, {}, data_dir=tmp)
            self.assertEqual(p._data, {"daily": {}})
            result = run(p.cmd_daily(FakeEvent("/运势")))
            self.assertIn("总评", result[0].text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
