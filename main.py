"""AstrBot 运势占卜插件：今日运势（连续占卜加成）、欧皇榜、星座、生肖、抽签、缘分配对"""

import hashlib
import json
import os
import random
import re
from datetime import datetime, timedelta

from astrbot.api import AstrBotConfig, logger
from astrbot.api.all import MessageEventResult
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.message_components import Plain
from astrbot.api.star import Context, Star, register

PLUGIN_NAME = "astrbot_plugin_fortune"
PLUGIN_AUTHOR = "云晓"
PLUGIN_DESC = "运势占卜：星座/生肖/每日运势/抽签/欧皇榜/缘分配对"
try:
    from .hub_bridge import HUB_PROTOCOL_VERSION, emit_hub_event
except ImportError:
    from hub_bridge import HUB_PROTOCOL_VERSION, emit_hub_event

PLUGIN_VERSION = "1.2.0"

# ==================== 内容库 ====================

# 幸运色（12 种）
LUCKY_COLORS = [
    "红色", "橙色", "黄色", "绿色", "青色", "蓝色",
    "紫色", "粉色", "金色", "银色", "白色", "棕色",
]

# 宜（12 种）
YI_LIST = [
    "出行", "会友", "谈判", "读书", "学习", "运动",
    "表白", "签约", "理财", "旅行", "聚会", "整理",
]

# 忌（12 种）
JI_LIST = [
    "熬夜", "冲动消费", "口舌之争", "暴饮暴食", "拖延", "冒险投资",
    "轻信他人", "久坐不动", "急躁冒进", "钻牛角尖", "借贷", "冲动决策",
]

# 一句话（15 条）
ONE_LINERS = [
    "今天适合微笑，好运正在赶来的路上。",
    "心怀善念，福气自会不期而至。",
    "保持热爱，生活处处有惊喜。",
    "机会偏爱有准备的人，今天多做一点准备。",
    "心若向阳，无畏悲伤。",
    "慢一点也没关系，每一步都算数。",
    "相信自己的判断，直觉今天很准。",
    "今日份的好运，从早睡早起开始。",
    "与其焦虑未来，不如珍惜当下。",
    "好运藏在每一次小小的坚持里。",
    "今天不妨主动一点，好事会主动靠近你。",
    "把烦恼丢进风里，把好运装进口袋。",
    "世界偶尔会打盹，但好运从不错过你。",
    "今天许下的心愿，明天就能看到回声。",
    "保持好奇，好运总会与你不期而遇。",
]

# 总评等级（5 档 × 每档 5 条评语 = 25 条）
GRADE_INFO = [
    {"grade": "上上吉", "star": "★★★★★", "min": 90, "max": 99, "comments": [
        "鸿运当头，诸事顺遂，把握今天的好势头。",
        "天时地利人和，今日万事皆宜。",
        "运势如虹，心想之事十有九成。",
        "气运加身，贵人频现，宜大胆行动。",
        "诸事顺意，财运亨通，尽情享受好运。",
    ]},
    {"grade": "上吉", "star": "★★★★☆", "min": 80, "max": 89, "comments": [
        "运势走高，虽有小事波折，无碍大局。",
        "时来运转，重要的事情适合今天去做。",
        "诸事平顺，只要稳扎稳打必有所获。",
        "福星照拂，机会已至，切莫迟疑。",
        "运势良好，宜主动出击，收获可期。",
    ]},
    {"grade": "中平", "star": "★★★☆☆", "min": 60, "max": 79, "comments": [
        "运势平稳，不惊不喜，平常心最难得。",
        "一切如常，按部就班即可，无需强求。",
        "小有起伏，耐心应对，风波自平。",
        "运势中庸，积蓄力量，静待时机。",
        "平平淡淡才是真，今日宜稳不宜急。",
    ]},
    {"grade": "小凶", "star": "★★☆☆☆", "min": 40, "max": 59, "comments": [
        "运势欠佳，诸事多磨，谨慎为上。",
        "小事不顺，莫要放在心上，过犹不及。",
        "运势偏弱，今日不宜做重大决定。",
        "小有波折，放平心态，明天会更好。",
        "时运一般，宜低调行事，保存实力。",
    ]},
    {"grade": "大凶", "star": "★☆☆☆☆", "min": 20, "max": 39, "comments": [
        "运势低迷，诸事不宜，今日宜休养生息。",
        "祸兮福之所倚，低谷之后必有反弹。",
        "运势不畅，谨言慎行，远离口舌是非。",
        "阴霾笼罩，不宜远行与投资，守成为上。",
        "运势晦暗，保持乐观，低谷不会太久。",
    ]},
]

# 总评等级生成权重（对应 GRADE_INFO 下标）
GRADE_WEIGHTS = [15, 25, 35, 15, 10]

# 通用今日忠告（12 条）
ADVICES = [
    "主动迈出第一步，好运自然相随。",
    "保持冷静，看清形势再行动。",
    "多倾听他人的意见，会有意外收获。",
    "今天适合学习和充电，为未来积蓄力量。",
    "抓住稍纵即逝的机会，别犹豫。",
    "与人为善，今日的人际关系格外重要。",
    "适度放慢节奏，张弛有度才是王道。",
    "大胆表达自己的想法，别把机会让给别人。",
    "关注细节，细节决定成败。",
    "保持乐观的心态，困难都是暂时的。",
    "今日宜专注，一次只做好一件事。",
    "勇于尝试新事物，说不定有惊喜。",
]

# 12 星座模板（日期区间 / 元素 / 性格描述 / 专属幸运色）
SIGNS = {
    "白羊座": {"date": "3.21-4.19", "element": "火象", "desc": "勇往直前，热情冲动，天生的行动派", "colors": ["红色", "橙色"]},
    "金牛座": {"date": "4.20-5.20", "element": "土象", "desc": "稳重踏实，执着坚持，最值得信赖的伙伴", "colors": ["绿色", "粉色"]},
    "双子座": {"date": "5.21-6.21", "element": "风象", "desc": "机智善变，好奇心旺盛，点子多才多艺", "colors": ["黄色", "白色"]},
    "巨蟹座": {"date": "6.22-7.22", "element": "水象", "desc": "温柔顾家，心思细腻，直觉异常敏锐", "colors": ["银色", "白色"]},
    "狮子座": {"date": "7.23-8.22", "element": "火象", "desc": "自信耀眼，慷慨大方，天生的领导者", "colors": ["金色", "橙色"]},
    "处女座": {"date": "8.23-9.22", "element": "土象", "desc": "细致严谨，追求完美，值得托付的细节控", "colors": ["灰色", "蓝色"]},
    "天秤座": {"date": "9.23-10.23", "element": "风象", "desc": "优雅从容，善于平衡，天生的协调者", "colors": ["粉色", "蓝色"]},
    "天蝎座": {"date": "10.24-11.22", "element": "水象", "desc": "深沉执着，洞察力惊人，爱憎分明", "colors": ["紫色", "黑色"]},
    "射手座": {"date": "11.23-12.21", "element": "火象", "desc": "自由乐观，热爱冒险，永远在路上", "colors": ["紫色", "蓝色"]},
    "摩羯座": {"date": "12.22-1.19", "element": "土象", "desc": "坚韧务实，目标明确，厚积薄发的实干家", "colors": ["棕色", "黑色"]},
    "水瓶座": {"date": "1.20-2.18", "element": "风象", "desc": "独立创新，思想前卫，不走寻常路", "colors": ["蓝色", "银色"]},
    "双鱼座": {"date": "2.19-3.20", "element": "水象", "desc": "浪漫感性，富有想象力，温柔多情", "colors": ["蓝色", "绿色"]},
}

# 星座别名映射（支持去"座"字与常用别名）
SIGN_ALIASES = {
    "白羊": "白羊座", "白羊座": "白羊座",
    "金牛": "金牛座", "金牛座": "金牛座",
    "双子": "双子座", "双子座": "双子座",
    "巨蟹": "巨蟹座", "巨蟹座": "巨蟹座",
    "狮子": "狮子座", "狮子座": "狮子座",
    "处女": "处女座", "处女座": "处女座",
    "天秤": "天秤座", "天秤座": "天秤座", "天平": "天秤座",
    "天蝎": "天蝎座", "天蝎座": "天蝎座",
    "射手": "射手座", "射手座": "射手座",
    "摩羯": "摩羯座", "摩羯座": "摩羯座", "山羊": "摩羯座",
    "水瓶": "水瓶座", "水瓶座": "水瓶座",
    "双鱼": "双鱼座", "双鱼座": "双鱼座",
}

# 12 生肖模板（性格描述 / 专属幸运色）
ZODIACS = {
    "鼠": {"desc": "机智灵活，善于应变，总能在细微处发现机会", "colors": ["蓝色", "金色"]},
    "牛": {"desc": "勤恳踏实，稳重可靠，一步一个脚印", "colors": ["绿色", "棕色"]},
    "虎": {"desc": "勇猛自信，魄力十足，天生的开拓者", "colors": ["红色", "橙色"]},
    "兔": {"desc": "温和聪慧，善解人意，人缘极佳", "colors": ["粉色", "白色"]},
    "龙": {"desc": "气度不凡，志向远大，自带贵气", "colors": ["金色", "红色"]},
    "蛇": {"desc": "睿智冷静，直觉敏锐，深藏不露", "colors": ["青色", "紫色"]},
    "马": {"desc": "自由奔放，行动力强，说走就走", "colors": ["红色", "棕色"]},
    "羊": {"desc": "温顺善良，细腻体贴，温柔有力量", "colors": ["黄色", "绿色"]},
    "猴": {"desc": "机灵聪颖，活泼好动，主意层出不穷", "colors": ["金色", "橙色"]},
    "鸡": {"desc": "勤勉守时，追求完美，一丝不苟", "colors": ["白色", "黄色"]},
    "狗": {"desc": "忠诚可靠，正直坦诚，最值得信赖", "colors": ["棕色", "蓝色"]},
    "猪": {"desc": "宽厚豁达，乐观知足，福气满满", "colors": ["粉色", "金色"]},
}

# 签文库（30 签：上上 6 + 上 8 + 中 10 + 下 6，均附解签文）
LOTS = [
    {"no": 1, "grade": "上上", "poem": "春风得意马蹄疾，一日看尽长安花。", "explain": "所求之事万事顺遂，眼下正是好时机，宜大胆行动。"},
    {"no": 2, "grade": "上上", "poem": "宝剑锋从磨砺出，梅花香自苦寒来。", "explain": "过往的付出终有回报，苦尽甘来，功名利禄渐入佳境。"},
    {"no": 3, "grade": "上上", "poem": "金鳞岂是池中物，一遇风云便化龙。", "explain": "大器晚成之象，时机一到自当一飞冲天，切勿妄自菲薄。"},
    {"no": 4, "grade": "上上", "poem": "柳暗花明又一村，峰回路转见晴天。", "explain": "眼下若有困局，很快便会豁然开朗，柳暗花明。"},
    {"no": 5, "grade": "上上", "poem": "天时地利人和聚，万事俱备东风来。", "explain": "内外皆顺，贵人相助，把握当下可成大事。"},
    {"no": 6, "grade": "上上", "poem": "一帆风顺行千里，五谷丰登喜满怀。", "explain": "财运与福气双双临门，安享成果，与身边人分享喜悦。"},
    {"no": 7, "grade": "上", "poem": "千里之行始于足下，稳扎稳打步步高。", "explain": "目标虽远，一步一个脚印终能抵达，今日宜踏实做事。"},
    {"no": 8, "grade": "上", "poem": "花开堪折直须折，莫待无花空折枝。", "explain": "良机稍纵即逝，该出手时就出手，犹豫只会错过。"},
    {"no": 9, "grade": "上", "poem": "山重水复疑无路，自有贵人暗相扶。", "explain": "遇到难关时会有贵人相助，保持谦和，自有转机。"},
    {"no": 10, "grade": "上", "poem": "小荷才露尖尖角，前程可期待时日。", "explain": "初现曙光，前景光明，只是还需时日沉淀。"},
    {"no": 11, "grade": "上", "poem": "近水楼台先得月，向阳花木易为春。", "explain": "占得先机，顺势而为，主动靠近机会必有收获。"},
    {"no": 12, "grade": "上", "poem": "精诚所至金石开，坚持不懈终有成。", "explain": "诚意与坚持能打动一切，坚持所爱必有回响。"},
    {"no": 13, "grade": "上", "poem": "海阔凭鱼跃，天高任鸟飞。", "explain": "天地广阔任你施展，放手去做，前景无量。"},
    {"no": 14, "grade": "上", "poem": "读书破万卷，下笔如有神。", "explain": "积累终见成效，今日所学他日必有大用。"},
    {"no": 15, "grade": "中", "poem": "欲速则不达，稳中求进方为道。", "explain": "凡事不可操之过急，放平心态，稳扎稳打方为上策。"},
    {"no": 16, "grade": "中", "poem": "纸上得来终觉浅，绝知此事要躬行。", "explain": "空想不如实践，迈出第一步，答案自会显现。"},
    {"no": 17, "grade": "中", "poem": "雾里看花水中月，拨开云雾见真章。", "explain": "真相暂时朦胧，不必着急，时间会给出答案。"},
    {"no": 18, "grade": "中", "poem": "不积跬步无以至千里，积少成多贵在恒。", "explain": "小事积累成大业，今日的坚持是明日的基石。"},
    {"no": 19, "grade": "中", "poem": "他山之石可以攻玉，虚心求教获益多。", "explain": "多听前辈与同伴的建议，能少走许多弯路。"},
    {"no": 20, "grade": "中", "poem": "东边日出西边雨，道是无晴却有晴。", "explain": "得失参半本是常态，平常心对待，自有意外之喜。"},
    {"no": 21, "grade": "中", "poem": "留得青山在，不愁没柴烧。", "explain": "保存实力，来日方长，眼下的退让是为了更好的前进。"},
    {"no": 22, "grade": "中", "poem": "塞翁失马焉知非福，眼前波折未必忧。", "explain": "祸福相依，暂时的不顺可能暗藏转机，放宽心。"},
    {"no": 23, "grade": "中", "poem": "行到水穷处，坐看云起时。", "explain": "顺其自然，静待转机，山穷水尽处自有柳暗花明。"},
    {"no": 24, "grade": "中", "poem": "流水落花春去也，且将新火试新茶。", "explain": "放下过去，轻装前行，新的开始就在眼前。"},
    {"no": 25, "grade": "下", "poem": "屋漏偏逢连夜雨，行船又遇打头风。", "explain": "时运不济，宜守不宜攻，谨言慎行度过低谷。"},
    {"no": 26, "grade": "下", "poem": "一叶障目不见泰山，当局者迷旁观清。", "explain": "多听身边人的劝告，勿钻牛角尖，退一步海阔天空。"},
    {"no": 27, "grade": "下", "poem": "逆水行舟用力撑，一篙松劲退千寻。", "explain": "正处逆流，此时松懈前功尽弃，咬牙坚持方能渡过。"},
    {"no": 28, "grade": "下", "poem": "好高骛远难成事，脚踏实地方长久。", "explain": "目标放低一些，从眼前小事做起，务实才是出路。"},
    {"no": 29, "grade": "下", "poem": "心急吃不了热豆腐，欲速不达反伤身。", "explain": "急躁是今日大敌，放慢节奏，冷静思考再行动。"},
    {"no": 30, "grade": "下", "poem": "前路崎岖多坎坷，谨慎前行防小人。", "explain": "近日需多加防范，少言慎行，重要事务可缓一缓。"},
]

# 缘分等级（分数下限 → (名称, 评语)；按分数从高到低匹配）
AFFINITY_LEVELS = [
    (95, "天作之合", "前世五百次回眸，才换来今生的相遇，请务必珍惜彼此！"),
    (85, "情投意合", "默契满分，聊什么都合拍，这段缘分值得用心经营。"),
    (70, "暗生情愫", "空气中似乎有些微妙的气氛，也许可以更进一步。"),
    (50, "缘分尚浅", "目前只是普通朋友，多制造相处机会或许会有转机。"),
    (0, "相看两厌", "磁场不太合拍，保持距离反而是种美好。"),
]

# 帮助文本
HELP_TEXT = (
    "🔮 运势占卜插件 v1.1.0\n"
    "━━━━━━━━━━━━━━━━━━━━━━\n"
    "📅 /运势            今日运势（每人每日一次，连续占卜有加成）\n"
    "🏆 /运势榜          群内今日欧皇榜（按分数 Top10）\n"
    "⭐ /星座 <星座名>   星座今日运势（支持 双鱼/双鱼座/水瓶 等别名）\n"
    "🐭 /生肖 <生肖>    生肖今日运势（如 牛 / 属牛 / 生肖牛）\n"
    "🎋 /抽签 <问题>    抽签占卜（同一问题当日结果一致）\n"
    "💞 /缘分 <对方>    缘分配对（@对方或输入名字，当日结果一致）\n"
    "❓ /占卜            显示本帮助"
)


@register(PLUGIN_NAME, PLUGIN_AUTHOR, PLUGIN_DESC, PLUGIN_VERSION)
class FortunePlugin(Star):
    HUB_PROTOCOL_VERSION = HUB_PROTOCOL_VERSION
    """运势占卜插件：今日运势、星座运势、生肖运势、抽签占卜"""

    def __init__(self, context: Context, config: AstrBotConfig = None, data_dir: str = None):
        super().__init__(context)
        self.config = config or {}
        # 数据目录（默认 plugins/plugin_data/astrbot_plugin_fortune）
        if data_dir:
            self.data_dir = data_dir
        else:
            self.data_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "plugin_data",
                PLUGIN_NAME,
            )
        os.makedirs(self.data_dir, exist_ok=True)
        self._data = {"daily": {}}
        self._load()
        logger.info(f"【{PLUGIN_NAME}】插件初始化完成，数据目录: {self.data_dir}")

    # ==================== 配置安全取值 ====================

    def _int_cfg(self, key: str, default: int) -> int:
        """安全读取整数配置：脏值（None/非数字）回退默认值"""
        v = self.config.get(key, default)
        try:
            return int(v) if v is not None else default
        except (TypeError, ValueError):
            return default

    def _bool_cfg(self, key: str, default: bool) -> bool:
        """安全读取布尔配置：脏值（不可识别）回退默认值"""
        v = self.config.get(key, default)
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            low = v.strip().lower()
            if low in ("1", "true", "yes", "on", "是"):
                return True
            if low in ("0", "false", "no", "off", "否", ""):
                return False
            return default
        if isinstance(v, (int, float)):
            return bool(v)
        return default

    # ==================== 数据持久化 ====================

    def _data_path(self) -> str:
        return os.path.join(self.data_dir, "fortune_data.json")

    def _load(self):
        """从磁盘加载持久化数据（结构校验，损坏/非预期格式时重置）"""
        try:
            path = self._data_path()
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and isinstance(data.get("daily"), dict):
                    self._data = data
                else:
                    logger.warning("运势占卜持久化数据格式异常，已重置")
        except Exception as e:
            logger.warning(f"加载运势占卜数据失败: {e}")

    def _save(self):
        """保存数据到磁盘（按配置保留天数清理过期记录）"""
        if not self._bool_cfg("enable_persistence", True):
            return
        try:
            keep_days = max(1, self._int_cfg("keep_days", 7))
            cutoff = (datetime.now() - timedelta(days=keep_days)).strftime("%Y-%m-%d")
            self._data["daily"] = {
                d: v for d, v in self._data["daily"].items() if d >= cutoff
            }
            with open(self._data_path(), "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"保存运势占卜数据失败: {e}")

    def _session_key(self, event: AstrMessageEvent) -> str:
        """会话唯一标识（优先 unified_msg_origin，回退 session）"""
        umo = getattr(event, "unified_msg_origin", None)
        if umo:
            return str(umo)
        return str(getattr(event, "session", "default"))

    def _user_key(self, event: AstrMessageEvent) -> str:
        """用户级键：会话|发送者ID（无发送者ID 时退化为会话键，兼容旧数据）"""
        session = self._session_key(event)
        try:
            uid = str(event.get_sender_id() or "").strip()
        except Exception:
            uid = ""
        return f"{session}|{uid}" if uid else session

    def _sender_name(self, event: AstrMessageEvent) -> str:
        """获取发送者昵称（失败返回空串）"""
        try:
            return str(event.get_sender_name() or "").strip()
        except Exception:
            return ""

    # ==================== 指令参数解析 ====================

    @staticmethod
    def parse_cmd_args(text: str, cmd: str) -> str:
        """解析指令参数：兼容带 /、／ 或不带斜杠的前缀，返回参数部分（去首尾空白）"""
        if not text:
            return ""
        m = re.match(rf"^[\\/／]?\s*{re.escape(cmd)}\s*(.*)$", text.strip())
        return m.group(1).strip() if m else ""

    def _args(self, event: AstrMessageEvent, cmd: str) -> str:
        """从事件消息文本中提取指令参数"""
        return self.parse_cmd_args(getattr(event, "message_str", ""), cmd)

    # ==================== 今日运势 ====================

    @staticmethod
    def _grade_for_score(score: int) -> dict:
        """按分数定位档位信息（GRADE_INFO 中包含该分数的档）"""
        for info in GRADE_INFO:
            if info["min"] <= score <= info["max"]:
                return info
        return GRADE_INFO[-1]

    def _generate_daily_fortune(self, streak: int = 1) -> dict:
        """随机生成一份今日运势内容（随机，当日稳定性由持久化保证）。

        连续占卜加成：连续第 N 天额外 +2 分/天，封顶 +10；加成后按最终分重新定档。
        """
        rnd = random.Random()
        idx = rnd.choices(range(len(GRADE_INFO)), weights=GRADE_WEIGHTS, k=1)[0]
        info = GRADE_INFO[idx]
        score = rnd.randint(info["min"], info["max"])
        # 连续占卜加成
        bonus = 0
        if self._bool_cfg("streak_bonus_enabled", True):
            bonus = min(10, max(0, streak - 1) * 2)
        if bonus > 0:
            score = min(99, score + bonus)
            info = self._grade_for_score(score)
        return {
            "score": score,
            "grade": info["grade"],
            "star": info["star"],
            "comment": rnd.choice(info["comments"]),
            "color": rnd.choice(LUCKY_COLORS),
            "number": rnd.randint(1, max(1, self._int_cfg("lucky_number_max", 99))),
            "yi": rnd.choice(YI_LIST),
            "ji": rnd.choice(JI_LIST),
            "line": rnd.choice(ONE_LINERS),
            "time": datetime.now().strftime("%H:%M"),
            "streak": int(streak),
            "bonus": int(bonus),
        }

    def _get_daily_fortune(self, event: AstrMessageEvent) -> tuple[dict, bool]:
        """获取用户今日运势：(内容, 是否今日新生成)。

        每用户每日一次：当日已生成则直接返回已存内容，否则生成并持久化。
        连续天数由昨日记录推算（昨日同键存在则 +1，否则从第 1 天开始）。
        """
        today = datetime.now().strftime("%Y-%m-%d")
        key = self._user_key(event)
        daily = self._data["daily"].setdefault(today, {})
        existing = daily.get(key)
        if existing:
            return existing, False
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        prev = self._data["daily"].get(yesterday, {}).get(key)
        try:
            streak = int(prev.get("streak", 0)) + 1 if prev else 1
        except (AttributeError, TypeError, ValueError):
            streak = 1
        fortune = self._generate_daily_fortune(streak)
        name = self._sender_name(event)
        if name:
            fortune["name"] = name[:20]
        else:
            try:
                uid = str(event.get_sender_id() or "").strip()
            except Exception:
                uid = ""
            if uid:
                fortune["name"] = f"用户{uid[-4:]}"
        # 会话记录数上限保护：超出时清理最旧记录（dict 有序，首个即最旧）
        max_records = max(1, self._int_cfg("max_daily_records", 1000))
        if len(daily) >= max_records:
            del daily[next(iter(daily))]
        daily[key] = fortune
        self._save()
        return fortune, True

    @staticmethod
    def _format_daily(fortune: dict, is_new: bool) -> str:
        """格式化今日运势输出"""
        today = datetime.now().strftime("%Y-%m-%d")
        lines = [
            f"🔮 今日运势 · {today}",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"📊 总评: {fortune['star']} {fortune['score']}分 · {fortune['grade']}",
            f"🎨 幸运色: {fortune['color']}",
            f"🔢 幸运数字: {fortune['number']}",
            f"✅ 宜: {fortune['yi']}",
            f"🚫 忌: {fortune['ji']}",
            f"💬 {fortune['comment']}",
            f"🌟 {fortune['line']}",
        ]
        try:
            streak = int(fortune.get("streak", 1))
        except (TypeError, ValueError):
            streak = 1
        if streak > 1:
            bonus = fortune.get("bonus", 0)
            if isinstance(bonus, (int, float)) and bonus > 0:
                lines.append(f"🔥 连续占卜 {streak} 天，获得加成 +{int(bonus)} 分")
            else:
                lines.append(f"🔥 连续占卜 {streak} 天")
        if not is_new:
            lines.append(f"⏱️ 今日已占卜过（{fortune['time']}），命运不变哦～")
        return "\n".join(lines)

    def _leaderboard_text(self, event: AstrMessageEvent) -> str:
        """渲染当前会话今日欧皇榜（按分数 Top10）"""
        today = datetime.now().strftime("%Y-%m-%d")
        prefix = self._session_key(event) + "|"
        rows = []
        for k, rec in self._data["daily"].get(today, {}).items():
            if not k.startswith(prefix):
                continue
            try:
                score = int(rec.get("score", 0))
            except (TypeError, ValueError):
                continue
            name = str(rec.get("name") or k.rsplit("|", 1)[-1])
            rows.append((score, name, str(rec.get("grade", ""))))
        if not rows:
            return (
                f"🏆 欧皇榜 · {today}\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                "📭 今天还没有人占卜过运势\n发送 /运势 抢占榜首吧！"
            )
        rows.sort(key=lambda r: -r[0])
        medals = ["🥇", "🥈", "🥉"]
        lines = [f"🏆 欧皇榜 · {today}（共 {len(rows)} 人占卜）", "━━━━━━━━━━━━━━━━━━━━━━"]
        for i, (score, name, grade) in enumerate(rows[:10]):
            icon = medals[i] if i < 3 else f"{i + 1}."
            display = name if len(name) <= 12 else name[:11] + "…"
            lines.append(f"{icon} {display} · {score}分 · {grade}")
        champion = rows[0]
        lines.append(f"👑 今日欧皇：{champion[1]}（{champion[0]} 分）")
        return "\n".join(lines)

    # ==================== 星座 / 生肖解析与运势 ====================

    @staticmethod
    def resolve_sign(raw: str) -> str:
        """解析星座名（支持别名，如 双鱼/双鱼座/水瓶/天平），未识别返回空串"""
        name = (raw or "").strip()
        if not name:
            return ""
        if name in SIGN_ALIASES:
            return SIGN_ALIASES[name]
        if name.endswith("座"):
            return SIGN_ALIASES.get(name[:-1], "")
        return ""

    @staticmethod
    def resolve_zodiac(raw: str) -> str:
        """解析生肖名（容忍 属牛/生肖牛 前缀），未识别返回空串"""
        name = (raw or "").strip().replace("生肖", "").replace("属", "")
        return name if name in ZODIACS else ""

    @staticmethod
    def _sign_fortune(sign: str, date: str) -> dict:
        """按"日期+星座"固定随机种子生成星座运势（同日同星座结果一致）"""
        rnd = random.Random(f"{date}|{sign}")
        info = SIGNS[sign]
        return {
            "overall": rnd.randint(60, 99),
            "love": rnd.randint(40, 99),
            "career": rnd.randint(40, 99),
            "wealth": rnd.randint(40, 99),
            "color": rnd.choice(info["colors"]),
            "number": rnd.randint(1, 99),
            "advice": rnd.choice(ADVICES),
        }

    @staticmethod
    def _zodiac_fortune(zodiac: str, date: str) -> dict:
        """按"日期+生肖"固定随机种子生成生肖运势（同日同生肖结果一致）"""
        rnd = random.Random(f"{date}|{zodiac}")
        info = ZODIACS[zodiac]
        return {
            "overall": rnd.randint(60, 99),
            "love": rnd.randint(40, 99),
            "career": rnd.randint(40, 99),
            "wealth": rnd.randint(40, 99),
            "color": rnd.choice(info["colors"]),
            "number": rnd.randint(1, 99),
            "advice": rnd.choice(ADVICES),
        }

    @staticmethod
    def _format_sign(sign: str, fortune: dict, date: str) -> str:
        """格式化星座运势输出"""
        info = SIGNS[sign]
        return "\n".join([
            f"🔮 {sign}今日运势 · {date}",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"✨ 综合指数: {fortune['overall']}/100",
            f"💖 爱情: {fortune['love']}/100  💼 事业: {fortune['career']}/100",
            f"💰 财运: {fortune['wealth']}/100",
            f"🎨 幸运色: {fortune['color']}  🔢 幸运数字: {fortune['number']}",
            f"📖 {sign}（{info['date']} · {info['element']}）: {info['desc']}",
            f"💡 今日忠告: {fortune['advice']}",
        ])

    @staticmethod
    def _format_zodiac(zodiac: str, fortune: dict, date: str) -> str:
        """格式化生肖运势输出"""
        info = ZODIACS[zodiac]
        return "\n".join([
            f"🐭 生肖{zodiac}今日运势 · {date}",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"✨ 综合指数: {fortune['overall']}/100",
            f"💖 爱情: {fortune['love']}/100  💼 事业: {fortune['career']}/100",
            f"💰 财运: {fortune['wealth']}/100",
            f"🎨 幸运色: {fortune['color']}  🔢 幸运数字: {fortune['number']}",
            f"📖 属{zodiac}者: {info['desc']}",
            f"💡 今日忠告: {fortune['advice']}",
        ])

    # ==================== 抽签 ====================

    @staticmethod
    def draw_lot(question: str, date: str) -> dict:
        """按"问题+日期"哈希取签（同一问题同日结果一致），返回签文 dict"""
        key = f"{date}|{question}".encode("utf-8")
        digest = int(hashlib.md5(key).hexdigest(), 16)
        return LOTS[digest % len(LOTS)]

    @staticmethod
    def _format_lot(lot: dict, question: str) -> str:
        """格式化抽签输出"""
        today = datetime.now().strftime("%Y-%m-%d")
        return "\n".join([
            f"🎋 抽签占卜 · {today}",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"❓ 所问: {question}",
            f"🏷️ 签级: {lot['grade']} · 第 {lot['no']} 签",
            f"📜 签诗: {lot['poem']}",
            f"💡 解签: {lot['explain']}",
        ])

    # ==================== 缘分配对 ====================

    @staticmethod
    def _affinity_score(a: str, b: str, date: str) -> int:
        """按"双方标识+日期"哈希生成缘分值（5~99，同日同对结果一致且与顺序无关）"""
        pair = sorted([str(a or "me"), str(b or "other")])
        digest = int(hashlib.md5(f"{date}|{pair[0]}|{pair[1]}".encode("utf-8")).hexdigest(), 16)
        return 5 + digest % 95

    @classmethod
    def _affinity_level(cls, score: int) -> tuple[str, str]:
        """按分数定位缘分等级：(名称, 评语)"""
        for min_score, name, comment in AFFINITY_LEVELS:
            if score >= min_score:
                return name, comment
        return AFFINITY_LEVELS[-1][1], AFFINITY_LEVELS[-1][2]

    def _format_affinity(self, me_name: str, other: str, score: int, date: str) -> str:
        """格式化缘分配对输出"""
        level, comment = self._affinity_level(score)
        hearts = "💕" * max(1, round(score / 20))
        return "\n".join([
            f"💞 缘分配对 · {date}",
            "━━━━━━━━━━━━━━━━━━━━━━",
            f"👫 {me_name} ❤️ {other}",
            f"{hearts}",
            f"💗 缘分值: {score}/100 · {level}",
            f"💬 {comment}",
        ])

    def _extract_at_target(self, event: AstrMessageEvent) -> str:
        """从消息组件中提取被 @ 者的 QQ 号（无则返回空串）"""
        try:
            from astrbot.api.message_components import At
            for comp in event.get_messages() or []:
                if isinstance(comp, At):
                    qq = str(getattr(comp, "qq", "") or "").strip()
                    if qq:
                        return qq
        except Exception:
            pass
        return ""

    # ==================== 指令处理 ====================

    @filter.command("运势", priority=200)
    async def cmd_daily(self, event: AstrMessageEvent) -> MessageEventResult:
        """今日运势（每人每日一次，同日重复查询返回当天已生成的运势）"""
        try:
            fortune, is_new = self._get_daily_fortune(event)
            if is_new:
                gid = ""
                try:
                    gid = str(event.get_group_id() or "")
                except Exception:
                    pass
                uid = str(event.get_sender_id() or "") if callable(getattr(event, "get_sender_id", None)) else self._user_key(event)
                emit_hub_event(PLUGIN_NAME, "fortune.drawn", {"user_id": uid, "nickname": fortune.get("name", ""), "score": int(fortune.get("score", 0)), "grade": fortune.get("grade", ""), "group_id": gid}, self.context)
            return self._send_text(event, self._format_daily(fortune, is_new))
        except Exception as e:
            logger.error(f"今日运势失败: {e}")
            return self._send_text(event, f"❌ 运势生成失败: {str(e)}")

    @filter.command("运势榜", priority=200)
    async def cmd_leaderboard(self, event: AstrMessageEvent) -> MessageEventResult:
        """群内今日欧皇榜：按当日已占卜的分数排序 Top10"""
        try:
            return self._send_text(event, self._leaderboard_text(event))
        except Exception as e:
            logger.error(f"欧皇榜查询失败: {e}")
            return self._send_text(event, f"❌ 欧皇榜生成失败: {str(e)}")

    @filter.command("星座", priority=200)
    async def cmd_sign(self, event: AstrMessageEvent) -> MessageEventResult:
        """星座今日运势（支持别名，同日同星座结果一致）"""
        sign = self.resolve_sign(self._args(event, "星座"))
        if not sign:
            return self._send_text(event, (
                "❌ 用法: /星座 <星座名>（如 双鱼 / 双鱼座 / 水瓶 / 天平）\n"
                "可用星座: 白羊 金牛 双子 巨蟹 狮子 处女 天秤 天蝎 射手 摩羯 水瓶 双鱼"
            ))
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            fortune = self._sign_fortune(sign, today)
            return self._send_text(event, self._format_sign(sign, fortune, today))
        except Exception as e:
            logger.error(f"星座运势失败: {e}")
            return self._send_text(event, f"❌ 星座运势生成失败: {str(e)}")

    @filter.command("生肖", priority=200)
    async def cmd_zodiac(self, event: AstrMessageEvent) -> MessageEventResult:
        """生肖今日运势（同日同生肖结果一致）"""
        zodiac = self.resolve_zodiac(self._args(event, "生肖"))
        if not zodiac:
            return self._send_text(event, (
                "❌ 用法: /生肖 <生肖>（如 牛 / 属牛 / 生肖牛）\n"
                "可用生肖: 鼠 牛 虎 兔 龙 蛇 马 羊 猴 鸡 狗 猪"
            ))
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            fortune = self._zodiac_fortune(zodiac, today)
            return self._send_text(event, self._format_zodiac(zodiac, fortune, today))
        except Exception as e:
            logger.error(f"生肖运势失败: {e}")
            return self._send_text(event, f"❌ 生肖运势生成失败: {str(e)}")

    @filter.command("抽签", priority=200)
    async def cmd_lot(self, event: AstrMessageEvent) -> MessageEventResult:
        """抽签占卜（同一问题同日结果一致）"""
        question = self._args(event, "抽签")
        if not question:
            return self._send_text(event, "❌ 用法: /抽签 <问题>\n例如: /抽签 今天适合表白吗")
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            lot = self.draw_lot(question, today)
            return self._send_text(event, self._format_lot(lot, question))
        except Exception as e:
            logger.error(f"抽签失败: {e}")
            return self._send_text(event, f"❌ 抽签失败: {str(e)}")

    @filter.command("占卜", priority=200)
    async def cmd_help(self, event: AstrMessageEvent) -> MessageEventResult:
        """运势占卜帮助列表"""
        return self._send_text(event, HELP_TEXT)

    @filter.command("缘分", priority=200)
    async def cmd_affinity(self, event: AstrMessageEvent) -> MessageEventResult:
        """缘分配对：/缘分 <@对方 | 名字>，同日同对结果一致且与发起顺序无关"""
        other = self._extract_at_target(event) or self._args(event, "缘分")
        if not other:
            return self._send_text(event, "❌ 用法: /缘分 <@对方 或 名字>\n例如: /缘分 小明")
        try:
            me_id = ""
            try:
                me_id = str(event.get_sender_id() or "").strip()
            except Exception:
                pass
            if not me_id:
                me_id = self._session_key(event)
            me_name = self._sender_name(event) or f"用户{me_id[-4:]}"
            today = datetime.now().strftime("%Y-%m-%d")
            score = self._affinity_score(me_id, other, today)
            return self._send_text(event, self._format_affinity(me_name, other, score, today))
        except Exception as e:
            logger.error(f"缘分配对失败: {e}")
            return self._send_text(event, f"❌ 缘分配对失败: {str(e)}")

    # ==================== 工具方法 ====================

    @staticmethod
    def _send_text(event, text: str) -> MessageEventResult:
        """构造纯文本回复结果"""
        return event.chain_result([Plain(text)])

    async def terminate(self):
        """插件卸载时保存数据"""
        try:
            self._save()
        except Exception:
            pass

    def hub_status(self) -> dict:
        today = datetime.now().strftime("%Y-%m-%d")
        today_cnt = len(self._data.get("daily", {}).get(today, {}) or {})
        return {
            "version": PLUGIN_VERSION,
            "status": "online",
            "metrics": {"今日占卜": today_cnt, "累计天数": len(self._data.get("daily", {}))},
            "actions": ["get_ranking"],
        }

    async def hub_action(self, action: str, params: dict | None = None) -> dict:
        if action == "get_ranking":
            today = datetime.now().strftime("%Y-%m-%d")
            recs = list((self._data.get("daily", {}).get(today, {}) or {}).values())
            recs.sort(key=lambda x: -int(x.get("score", 0)))
            return {"ok": True, "data": {"date": today, "top": [{"name": r.get("name", ""), "score": r.get("score", 0), "grade": r.get("grade", "")} for r in recs[:10]]}}
        return {"ok": False, "error": f"不支持的动作：{action}"}
