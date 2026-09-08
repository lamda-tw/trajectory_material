from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SignalPattern:
    label: str
    regex: str
    roles: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class IndicatorDefinition:
    check_id: str
    title: str
    dimension: str
    max_score: float
    failure_tag: str
    conclusion: str
    expected: str
    recommendation: str
    failure_patterns: tuple[SignalPattern, ...]
    pass_patterns: tuple[SignalPattern, ...] = ()
    gate_id: str = ""


USER = ("用户", "user")
ASSISTANT = ("AI", "assistant")


INDICATORS: tuple[IndicatorDefinition, ...] = (
    IndicatorDefinition(
        "D1", "数据来源可追溯", "data", 3, "source_fabrication",
        "轨迹暴露了无法追溯或凭空引入的数据源。",
        "每个输入角色均能追到用户提供的文件、sheet 和路径。",
        "输出输入清单及来源证据，禁止使用未确认文件名。",
        (
            SignalPattern("用户质疑delivery_plan来源", r"where\s+(?:is\s+)?(?:this\s+)?delivery_plan\.xlsx.*from", USER),
            SignalPattern("agent承认文件不存在", r"delivery_plan\.xlsx\s+(?:doesn['’]?t|does not)\s+exist\s+as\s+a\s+separate\s+file", ASSISTANT),
        ),
        (SignalPattern("来源清单已核验", r"source manifest.*verified|输入清单.*已核验", ASSISTANT),),
        "DATA_SOURCE_FABRICATION",
    ),
    IndicatorDefinition(
        "D2", "WSD数量字段优先级", "data", 5, "field_mapping",
        "WSD 数量字段选择错误，导致有效物料或 DU 被过滤。",
        "优先使用 QTY (Use This)，仅在规则允许时回退 Quantity (Dont Use)。",
        "把字段优先级固化为契约，并对两列冲突、空值做统计门禁。",
        (
            SignalPattern("agent定位错误数量列", r"quantity\s*\(dont use\).*empty.*(?:actual quantity|actual quantities).*qty\s*\(use this\)", ASSISTANT),
            SignalPattern("cleaner读取错误列", r"cleaner\s+only\s+read.*quantity\s*\(dont use\)", ASSISTANT),
        ),
        (SignalPattern("字段优先级验证", r"qty\s*\(use this\).*preferred.*fallback.*quantity\s*\(dont use\)", ASSISTANT),),
        "CORE_WSD_FIELD_MAPPING",
    ),
    IndicatorDefinition(
        "D4", "本地与服务器输入版本一致", "data", 4, "stale_input",
        "本地与服务器使用了不同输入版本或旧产物。",
        "本地、服务器及页面使用同一输入清单和 run_id/hash。",
        "部署时上传输入清单、记录 hash，并将 run_id 写入 CSV 与页面。",
        (
            SignalPattern("服务器输入不同", r"server\s+(?:reads|is reading).*input.*different|input data being different between local and server", ASSISTANT),
            SignalPattern("本地与服务器数字不同", r"server numbers.*differ.*local", ASSISTANT),
        ),
        (SignalPattern("版本一致验证", r"local.*server.*(?:same|match).*(?:hash|run[_ -]?id)|(?:hash|run[_ -]?id).*match", ASSISTANT),),
    ),
    IndicatorDefinition(
        "S1", "周字段规范化", "schedule", 3, "week_parse",
        "周字段解析失败，导致计划行静默丢失或落周错误。",
        "JUN/JUL - WK27 等混合周字段能归一并保留全部 DU。",
        "建立显式周格式解析器、异常清单和跨年排序测试。",
        (
            SignalPattern("用户要求混合周归一", r"jun/jul\s*-\s*wk27.*normalize", USER),
            SignalPattern("agent承认正则失败", r"regex.*fails?\s+on.*jun/jul|jun/jul.*silently dropped", ASSISTANT),
        ),
        (SignalPattern("混合周锚点验证", r"jun/jul.*(?:2026-w27|jul\s*-\s*wk27).*(?:verified|correct)", ASSISTANT),),
    ),
    IndicatorDefinition(
        "S2", "月计划保持完整DU落周", "schedule", 4, "du_atomicity",
        "月计划曾把同一 DU 的物料拆分到多个周。",
        "同一 DU 的全部 BBOM 必须落在同一周。",
        "按 DU 分配周次，再由 DU 周次驱动物料需求，禁止按物料平均拆周。",
        (
            SignalPattern("用户指出DU不可拆周", r"can\s*not\s+split.*same\s+du.*different\s+week", USER),
            SignalPattern("agent承认拆分逻辑错误", r"logic.*(?:split|splits).*du.*(?:wrong|incorrect)|把一个\s*du\s*的需求拆分.*错误", ASSISTANT),
        ),
        (SignalPattern("完整DU落周验证", r"each\s+du.*(?:single|one)\s+week.*verified|每个\s*du.*完整.*单周", ASSISTANT),),
        "DU_SPLIT_ACROSS_WEEKS",
    ),
    IndicatorDefinition(
        "S4", "活跃DU覆盖率", "schedule", 3, "coverage_or_status",
        "应处理 DU 在排程或需求结果中静默缺失。",
        "每个活跃 DU 恰好有一个合法结果或明确排除原因。",
        "输出 expected/covered/excluded/unmatched 四张集合及覆盖率。",
        (
            SignalPattern("用户报告DU缺失", r"(?:the\s+)?du(?:s)?\s+below\s+(?:is|are)\s+missing", USER),
            SignalPattern(
                "agent确认管道丢DU",
                r"\bdu(?:s)?\b[^\n]{0,160}(?:lost|missing)[^\n]{0,120}(?:pipeline|output)|"
                r"\bdu(?:s)?\b[^\n]{0,160}silently\s+dropped",
                ASSISTANT,
            ),
        ),
        (SignalPattern("覆盖率验证", r"coverage.*100%|all\s+active\s+dus?.*unique", ASSISTANT),),
    ),
    IndicatorDefinition(
        "P2", "MR与状态后的有效需求", "simulation", 5, "effective_demand",
        "MR 或 DU 状态抵扣被应用到错误层级，导致已预留物料仍显示缺货。",
        "effective_demand=max(WSD-MR,0)，状态规则在 DU 层决定是否产生需求。",
        "按 DU_ID+BBOM 关联预留，输出原始需求、MR和有效需求。",
        (
            SignalPattern("用户报告MR后仍缺货", r"material reserve type is mr.*there should not have any shortage", USER),
            SignalPattern("agent承认MR抵扣层级错误", r"mr should offset demand|effective demand\s*=\s*(?:wsd|.*wsd).*mr", ASSISTANT),
        ),
        (SignalPattern("有效需求锚点验证", r"wsd.*mr.*effective demand.*(?:verified|no shortage|correct)", ASSISTANT),),
        "MR_DEMAND_REVERSED",
    ),
    IndicatorDefinition(
        "P3", "库存滚动连续守恒", "simulation", 6, "inventory_rollforward",
        "库存滚动公式丢失初始库存或重复累计历史缺口。",
        "首周含 on-hand，后续 opening[w+1]=closing[w]，历史缺口不重复计入净变动。",
        "显式输出 opening/inbound/demand/closing 并逐周做守恒断言。",
        (
            SignalPattern("异常指数缺口", r"8[,.]?388[,.]?608", USER + ASSISTANT),
            SignalPattern("用户报告有库存却负余额", r"cumulative balance already\s*-1.*next week.*on-?hand", USER),
            SignalPattern("agent承认缺口翻倍", r"shortage doubles each week|negative cumulative_balance.*carried forward", ASSISTANT),
            SignalPattern("agent承认初始库存丢失", r"on-?hand.*(?:lost|ignored)|丢了\s*onhand|onhand\s*被.*丢", ASSISTANT),
        ),
        (SignalPattern("库存守恒验证", r"inventory.*(?:roll|reconciliation|conservation).*(?:pass|verified)|库存.*守恒.*通过", ASSISTANT),),
        "INVENTORY_NOT_CONSERVED",
    ),
    IndicatorDefinition(
        "P4", "DU缺货数量上界", "simulation", 6, "shortage_allocation",
        "全仓累计缺口被直接复制到单个 DU，超过该 DU 的有效需求。",
        "0 <= DU Shortage_Qty <= DU effective_demand。",
        "按 DU-BBOM-周分配缺口并加入上下界断言和固定锚点。",
        (
            SignalPattern("用户报告单DU缺口过大", r"shortage_qty\s+is\s+not\s+so\s+right.*require\s+only\s+1", USER),
            SignalPattern("agent确认复制累计缺口", r"directly\s+from\s+supplyrecord\.shortage_qty|entire.*cumulative.*shortage.*du", ASSISTANT),
        ),
        (SignalPattern("DU缺口上界验证", r"shortage_qty.*(?:capped|<=|at most).*du.*(?:demand|effective)", ASSISTANT),),
    ),
    IndicatorDefinition(
        "O2", "页面与本轮CSV一致", "output", 4, "frontend_data_binding",
        "页面展示了旧 CSV 或与 model output 不一致的数据。",
        "页面、服务器 CSV 与本轮代码共享同一 run_id，抽样值完全一致。",
        "部署后对 DU-BBOM、KPI 和分组值做三类线上对账。",
        (
            SignalPattern(
                "用户报告页面数据不一致",
                r"dashboa?r?d data\s+(?:does\s+)?not match(?:\s+with)?.*output data|"
                r"dashboard.*not correct.*summary",
                USER,
            ),
            SignalPattern("agent承认服务器CSV旧", r"server-side csv data is old|csv files on the server still have the old", ASSISTANT),
        ),
        (SignalPattern("页面CSV对账通过", r"dashboard.*csv.*match.*verified|页面.*csv.*一致.*验证", ASSISTANT),),
        "FRONTEND_DATA_MISMATCH",
    ),
    IndicatorDefinition(
        "O5", "直接链接与构建产物可用", "output", 3, "deployment_artifact",
        "部署后的直接链接为空、页面无数据或构建资源路径错误。",
        "用户给定直接 URL 可打开，资源路径正确且页面烟测无错误。",
        "验证 dist asset base、直接 URL、控制台错误和关键组件数据。",
        (
            SignalPattern("用户看不到页面", r"do not see any dashboard|dashboard link is empty|dashboard now is shown no info|showing no data in the dashboard", USER),
            SignalPattern("agent确认资源路径错误", r"broken asset paths|asset paths.*(?:wrong|incorrect)|resource paths.*incorrect", ASSISTANT),
        ),
        (SignalPattern("线上页面烟测通过", r"dashboard.*loaded.*0\s+console errors|direct url.*(?:working|verified)", ASSISTANT),),
        "DASHBOARD_UNUSABLE",
    ),
)


TOTAL_MAX_SCORE = sum(item.max_score for item in INDICATORS) + 4.0
