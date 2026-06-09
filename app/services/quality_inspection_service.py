from __future__ import annotations

from app.schemas.quality_inspection import (
    DefectClassificationResult,
    DefectPatternInfo,
    DefectRecord,
    DefectSeverity,
    HistoricalDefect,
    InspectionContext,
    InspectionItem,
    QualityIndicatorResult,
    QualityStandard,
    RecommendationItem,
    RootCauseCategory,
    RootCauseResult,
)

# ── 严重度排序（用于优先级比较） ──────────────────────────────

SEVERITY_ORDER: dict[DefectSeverity, int] = {
    "critical": 0,
    "major": 1,
    "minor": 2,
}


# ══════════════════════════════════════════════════════════════════
# QualityInspectionService
# ══════════════════════════════════════════════════════════════════


class QualityInspectionService:
    """质量检测与缺陷分析核心业务服务。

    职责：
    - 质检指标判定
    - 缺陷分类与聚合
    - 缺陷模式识别
    - 人机料法环根因追溯
    - 改进建议生成

    不直接访问数据库、不直接调用模型客户端。
    """

    # ── RAG 预留接口 ──────────────────────────────────────────

    @staticmethod
    def match_quality_standard(
        product_id: str,
        metric_name: str,
        quality_standards: list[QualityStandard],
    ) -> QualityStandard | None:
        """根据产品 + 指标名称匹配质量标准。

        **当前实现**：精确匹配 product_id + metric_name。
        **RAG 扩展预留**：未来可替换为 embedding 语义检索，
        支持模糊匹配相近指标名称或跨产品标准推荐，
        并返回匹配证据与置信度。
        """
        for std in quality_standards:
            if std.product_id == product_id and std.metric_name == metric_name:
                return std
        return None

    @staticmethod
    def match_historical_defect(
        product_id: str,
        process_step: str,
        defect_type: str,
        historical_defects: list[HistoricalDefect],
    ) -> HistoricalDefect | None:
        """根据产品 + 工序 + 缺陷类型匹配历史缺陷记录。

        **当前实现**：精确匹配 product_id + process_step + defect_type。
        **RAG 扩展预留**：未来可替换为向量检索，
        支持语义匹配相似缺陷描述、跨产品缺陷案例推荐，
        并返回匹配证据与置信度。
        """
        for hd in historical_defects:
            if (
                hd.product_id == product_id
                and hd.process_step == process_step
                and hd.defect_type == defect_type
            ):
                return hd
        return None

    # ── 质检指标判定 ──────────────────────────────────────────

    @staticmethod
    def judge_all_indicators(
        items: list[InspectionItem],
        product_id: str,
        quality_standards: list[QualityStandard] | None = None,
    ) -> list[QualityIndicatorResult]:
        """批量判定质检指标。

        为每个 item 匹配质量标准（优先 quality_standards 中
        同 product_id + metric_name 的记录）。
        """
        standards = quality_standards or []
        results: list[QualityIndicatorResult] = []

        for item in items:
            # 按 product_id + metric_name 精确匹配
            matched_std = QualityInspectionService.match_quality_standard(
                product_id, item.metric_name, standards
            )

            standard_source = "inspection_items"
            std_min = item.standard_min
            std_max = item.standard_max

            if matched_std is not None:
                standard_source = "quality_standards"
                std_min = (
                    matched_std.standard_min
                    if matched_std.standard_min is not None
                    else std_min
                )
                std_max = (
                    matched_std.standard_max
                    if matched_std.standard_max is not None
                    else std_max
                )

            # 无标准场景
            if std_min is None and std_max is None:
                results.append(
                    QualityIndicatorResult(
                        item_id=item.item_id,
                        metric_name=item.metric_name,
                        measured_value=item.measured_value,
                        unit=item.unit,
                        passed=False,
                        deviation=0.0,
                        standard_source="none",
                        note=f"指标 {item.metric_name} 缺少质量标准且无自带上下限",
                    )
                )
                continue

            below_min = std_min is not None and item.measured_value < std_min
            above_max = std_max is not None and item.measured_value > std_max

            if below_min or above_max:
                # deviation: 低于下限为负，超过上限为正
                deviation = 0.0
                if below_min and std_min is not None:
                    deviation = round(item.measured_value - std_min, 4)
                elif above_max and std_max is not None:
                    deviation = round(item.measured_value - std_max, 4)

                detail_parts: list[str] = []
                if below_min:
                    detail_parts.append(f"低于下限 {std_min}")
                if above_max:
                    detail_parts.append(f"超过上限 {std_max}")

                results.append(
                    QualityIndicatorResult(
                        item_id=item.item_id,
                        metric_name=item.metric_name,
                        measured_value=item.measured_value,
                        standard_min=std_min,
                        standard_max=std_max,
                        unit=item.unit,
                        passed=False,
                        deviation=deviation,
                        standard_source=standard_source,
                        note=(
                            f"不合格：实测 {item.measured_value}{item.unit}，"
                            + "；".join(detail_parts)
                        ),
                    )
                )
            else:
                results.append(
                    QualityIndicatorResult(
                        item_id=item.item_id,
                        metric_name=item.metric_name,
                        measured_value=item.measured_value,
                        standard_min=std_min,
                        standard_max=std_max,
                        unit=item.unit,
                        passed=True,
                        deviation=0.0,
                        standard_source=standard_source,
                        note="合格",
                    )
                )

        return results

    # ── 缺陷分类与聚合 ────────────────────────────────────────

    @staticmethod
    def classify_defects(
        defect_records: list[DefectRecord],
    ) -> DefectClassificationResult:
        """对缺陷记录按类型、严重度、位置进行分类聚合。

        使用 DefectRecord.count 进行数量聚合（兼容 quantity 别名输入）。
        """
        by_type: dict[str, int] = {}
        by_severity: dict[str, int] = {}
        by_location: dict[str, int] = {}
        critical_items: list[str] = []

        for record in defect_records:
            # 按类型聚合（使用 count 字段）
            dt = record.defect_type.strip()
            if dt:
                by_type[dt] = by_type.get(dt, 0) + record.count

            # 按严重度聚合
            sev = record.severity
            by_severity[sev] = by_severity.get(sev, 0) + record.count

            # 按位置聚合
            loc = record.location.strip()
            if loc:
                by_location[loc] = by_location.get(loc, 0) + record.count

            # 记录 critical 缺陷 ID
            if sev == "critical":
                critical_items.append(record.defect_id)

        # 最高频缺陷类型
        top_type = ""
        if by_type:
            top_type = max(by_type, key=lambda k: by_type[k])

        total = sum(by_type.values())

        return DefectClassificationResult(
            total_defects=total,
            by_type=by_type,
            by_severity=by_severity,
            by_location=by_location,
            critical_items=critical_items,
            top_defect_type=top_type,
        )

    # ── 缺陷模式识别 ──────────────────────────────────────────

    @staticmethod
    def detect_patterns(
        classification: DefectClassificationResult,
        defect_records: list[DefectRecord],
        threshold: int = 10,
    ) -> DefectPatternInfo:
        """识别缺陷模式。

        支持：
        - 同一 defect_type 的 count 聚合
        - 同一 location 的缺陷聚合
        - 批次内缺陷总数统计
        - 识别高频缺陷类型（count >= threshold）
        """
        pattern_detected = False
        pattern_type = ""
        detail_parts: list[str] = []
        high_freq: list[str] = []
        location_clusters: list[str] = []

        # 高频缺陷类型
        for defect_type, cnt in classification.by_type.items():
            if cnt >= threshold:
                pattern_detected = True
                high_freq.append(defect_type)
                if not pattern_type:
                    pattern_type = "frequency"

        if high_freq:
            detail_parts.append(
                f"高频缺陷类型（>= {threshold} 次）：" + "、".join(high_freq)
            )

        # 位置聚类
        for location, cnt in classification.by_location.items():
            if cnt >= threshold:
                pattern_detected = True
                location_clusters.append(location)
                if pattern_type == "":
                    pattern_type = "location"

        if location_clusters:
            detail_parts.append(
                f"缺陷集中位置（>= {threshold} 次）：" + "、".join(location_clusters)
            )

        # 批次总数统计
        total = classification.total_defects
        if total >= threshold * 2:
            if not pattern_detected:
                pattern_detected = True
                pattern_type = "batch_quantity"
            detail_parts.append(f"批次缺陷总数 {total}，超出预警线")

        return DefectPatternInfo(
            pattern_detected=pattern_detected,
            pattern_type=pattern_type,
            detail="；".join(detail_parts) if detail_parts else "未检测到显著缺陷模式",
            high_frequency_types=high_freq,
            location_clusters=location_clusters,
            total_defects_in_batch=total,
        )

    # ── 人机料法环根因追溯 ────────────────────────────────────

    @staticmethod
    def trace_root_cause(
        defect_type: str,
        product_id: str,
        process_step: str,
        historical_defects: list[HistoricalDefect],
        environment_data: dict[str, float] | None = None,
        context: InspectionContext | None = None,
    ) -> RootCauseResult:
        """追溯缺陷根因。

        优先匹配历史缺陷（product_id + process_step + defect_type），
        匹配成功时返回历史根因信息。
        没有历史匹配时，基于 context + 规则推断。
        """
        env = environment_data or {}

        # 优先：历史缺陷匹配
        matched = QualityInspectionService.match_historical_defect(
            product_id, process_step, defect_type, historical_defects
        )
        if matched is not None and matched.root_cause_category != "unknown":
            evidence_lines = [
                f"历史记录 {matched.record_id or '(无编号)'}：{matched.root_cause}",
                f"历史发生 {matched.occurrence_count} 次",
            ]
            if matched.corrective_action:
                evidence_lines.append(f"纠正措施：{matched.corrective_action}")
            return RootCauseResult(
                root_cause_category=matched.root_cause_category,
                root_cause=matched.root_cause,
                confidence=0.85,
                matched_evidence=evidence_lines,
                corrective_action=matched.corrective_action,
                match_source="historical",
            )

        # 次级：基于上下文 + 规则推断
        result = QualityInspectionService._rule_based_root_cause(
            defect_type, process_step, env, context
        )
        # 如果历史有记录但类别为 unknown，补充匹配信息
        if matched is not None:
            result.matched_evidence.append(
                f"存在历史记录 {matched.record_id or '(无编号)'}，但根因未明确"
            )

        return result

    @staticmethod
    def _rule_based_root_cause(
        defect_type: str,
        process_step: str,
        environment_data: dict[str, float],
        context: InspectionContext | None = None,
    ) -> RootCauseResult:
        """基于规则的根因推断。

        优先使用 InspectionContext 提供的现场信息，
        其次使用 defect_type 关键词匹配，
        最后使用工序名称兜底推断。
        """
        defect_lower = defect_type.lower()
        ctx = context  # shorthand

        # ── 1. context 驱动的推断（优先级最高） ──

        # context.environment
        context_env = ctx.environment if ctx else {}
        merged_env = {**context_env, **environment_data}  # environment_data 兼容覆盖
        temp = merged_env.get("temperature", merged_env.get("温度", 25.0))
        humidity = merged_env.get("humidity", merged_env.get("湿度", 50.0))

        if temp > 40.0:
            return RootCauseResult(
                root_cause_category="environment",
                root_cause=(
                    f"环境温度异常（{temp}°C 超出正常范围），"
                    "可能导致材料膨胀或加工精度下降"
                ),
                confidence=0.70,
                matched_evidence=[f"环境温度 {temp}°C > 40°C"],
                corrective_action="检查并调节车间温控系统，确保温度在标准范围内。",
                match_source="rule_based",
            )
        if temp < 0.0:
            return RootCauseResult(
                root_cause_category="environment",
                root_cause=f"环境温度过低（{temp}°C），可能导致材料脆化或润滑失效",
                confidence=0.70,
                matched_evidence=[f"环境温度 {temp}°C < 0°C"],
                corrective_action="检查车间供暖系统，确保温度在标准范围内。",
                match_source="rule_based",
            )
        if humidity > 85.0:
            return RootCauseResult(
                root_cause_category="environment",
                root_cause=f"环境湿度过高（{humidity}%），可能导致材料锈蚀或电气故障",
                confidence=0.70,
                matched_evidence=[f"环境湿度 {humidity}% > 85%"],
                corrective_action="检查并启动除湿设备，确保湿度在标准范围内。",
                match_source="rule_based",
            )

        # context.machine_id / material_batch_id / operator_id 驱动
        if ctx:
            if ctx.machine_id:
                # 提供了设备信息 → 结合 defect_type 判断
                if any(
                    kw in defect_lower
                    for kw in [
                        "尺寸超差", "尺寸偏差", "size", "dimension",
                        "表面粗糙", "粗糙度", "roughness", "surface",
                        "外径", "内径", "直径", "划伤", "scratch",
                        "毛刺", "burr", "振纹", "chatter",
                    ]
                ):
                    return RootCauseResult(
                        root_cause_category="machine",
                        root_cause=(
                            f"缺陷 '{defect_type}' 涉及设备 {ctx.machine_id}，"
                            f"工序 '{process_step}'，"
                            "推测与设备精度、刀具状态或装夹有关"
                        ),
                        confidence=0.72,
                        matched_evidence=[
                            f"关联设备：{ctx.machine_id}",
                            f"缺陷类型 {defect_type} 属于设备相关缺陷",
                        ],
                        corrective_action=(
                            f"检查设备 {ctx.machine_id} 的精度、刀具及装夹状态。"
                        ),
                        match_source="rule_based",
                    )

            if ctx.material_batch_id:
                if any(
                    kw in defect_lower
                    for kw in [
                        "裂纹", "crack", "夹杂", "inclusion",
                        "硬度", "hardness", "气孔", "porosity",
                        "材料", "material", "成分", "composition",
                    ]
                ):
                    return RootCauseResult(
                        root_cause_category="material",
                        root_cause=(
                            f"缺陷 '{defect_type}' 关联材料批次 {ctx.material_batch_id}，"
                            "可能与原材料质量相关"
                        ),
                        confidence=0.72,
                        matched_evidence=[
                            f"关联材料批次：{ctx.material_batch_id}",
                            f"缺陷类型 {defect_type} 属于材料类缺陷",
                        ],
                        corrective_action=(
                            f"追溯材料批次 {ctx.material_batch_id} 的供应商及来料检验记录。"
                        ),
                        match_source="rule_based",
                    )

            if ctx.operator_id:
                # 操作者相关关键词
                if any(
                    kw in defect_lower
                    for kw in [
                        "操作", "operator", "人为", "manual",
                        "漏检", "误判", "装夹", "clamping",
                        "漏工序", "跳序",
                    ]
                ):
                    return RootCauseResult(
                        root_cause_category="man",
                        root_cause=(
                            f"缺陷 '{defect_type}' 涉及操作者 {ctx.operator_id}，"
                            "可能与操作规范性相关"
                        ),
                        confidence=0.68,
                        matched_evidence=[
                            f"关联操作者：{ctx.operator_id}",
                            f"缺陷类型 {defect_type} 属于人员操作相关缺陷",
                        ],
                        corrective_action=(
                            f"核查操作者 {ctx.operator_id} 的培训记录与操作合规性。"
                        ),
                        match_source="rule_based",
                    )

            if ctx.process_params:
                # 工艺参数异常
                return RootCauseResult(
                    root_cause_category="method",
                    root_cause=(
                        f"缺陷 '{defect_type}' 发生在工序 '{process_step}'，"
                        f"关联工艺参数：{ctx.process_params}，"
                        "推测与工艺参数设置或执行偏差相关"
                    ),
                    confidence=0.62,
                    matched_evidence=[
                        f"关联工艺参数：{ctx.process_params}",
                    ],
                    corrective_action=(
                        "复查工序工艺参数设定值与实际值，"
                        "确认参数是否在工艺规范允许范围内。"
                    ),
                    match_source="rule_based",
                )

        # ── 2. defect_type 关键词匹配 ──

        # machine 关键词
        machine_keywords = [
            "尺寸超差", "尺寸偏差", "size", "dimension",
            "表面粗糙", "粗糙度", "roughness", "surface",
            "外径", "内径", "直径", "outer_diameter", "inner_diameter", "diameter",
            "圆度", "roundness", "平面度", "flatness",
            "同轴度", "垂直度", "跳动", "runout",
            "划伤", "scratch", "毛刺", "burr",
            "刀纹", "tool_mark", "振纹", "chatter",
        ]
        if any(kw in defect_lower for kw in machine_keywords):
            evidence = [
                f"缺陷类型 {defect_type} 属于尺寸/表面质量类缺陷",
                f"发生在工序 {process_step}",
            ]
            if ctx and ctx.machine_id:
                evidence.insert(0, f"关联设备：{ctx.machine_id}")
            return RootCauseResult(
                root_cause_category="machine",
                root_cause=(
                    f"缺陷类型 '{defect_type}' 与加工设备精度/状态相关，"
                    f"工序 '{process_step}' 涉及的设备可能存在："
                    "刀具磨损、主轴跳动、导轨间隙或装夹偏差"
                ),
                confidence=0.65,
                matched_evidence=evidence,
                corrective_action=(
                    "建议：1) 检查设备精度与校准状态；"
                    "2) 检查刀具磨损情况并更换；"
                    "3) 复查工装夹具定位精度。"
                ),
                match_source="rule_based",
            )

        # material 关键词
        material_keywords = [
            "裂纹", "crack", "夹杂", "inclusion",
            "硬度", "hardness", "气孔", "porosity",
            "缩松", "缩孔", "材料", "material",
            "成分", "composition", "偏析", "segregation",
            "锈蚀", "corrosion", "氧化", "oxidation",
        ]
        if any(kw in defect_lower for kw in material_keywords):
            evidence = [f"缺陷类型 {defect_type} 属于材料类缺陷"]
            if ctx and ctx.material_batch_id:
                evidence.insert(0, f"关联材料批次：{ctx.material_batch_id}")
            return RootCauseResult(
                root_cause_category="material",
                root_cause=(
                    f"缺陷类型 '{defect_type}' 与材料特性相关，"
                    "可能原因：原材料批次质量问题、材料成分偏差、热处理工艺不当"
                ),
                confidence=0.65,
                matched_evidence=evidence,
                corrective_action=(
                    "建议：1) 追溯原材料批次与供应商；"
                    "2) 对原材料进行复检（成分、金相）；"
                    "3) 检查热处理工艺参数。"
                ),
                match_source="rule_based",
            )

        # method 关键词
        method_keywords = [
            "工艺", "process", "参数", "parameter",
            "温度", "temperature", "压力", "pressure",
            "时间", "time", "速度", "speed",
            "进给", "feed", "切削", "cutting",
            "冷却", "coolant", "润滑", "lubrication",
        ]
        if any(kw in defect_lower for kw in method_keywords):
            return RootCauseResult(
                root_cause_category="method",
                root_cause=(
                    f"缺陷类型 '{defect_type}' 与工艺参数相关，"
                    "可能原因：加工参数设置不当、工艺流程顺序不合理、工艺规范不完整"
                ),
                confidence=0.60,
                matched_evidence=[f"缺陷类型 {defect_type} 属于工艺类缺陷"],
                corrective_action=(
                    "建议：1) 复查并优化当前工序工艺参数；"
                    "2) 检查工艺规范是否覆盖该缺陷场景；"
                    "3) 对操作人员进行工艺培训。"
                ),
                match_source="rule_based",
            )

        # man 关键词
        man_keywords = [
            "操作", "operator", "人为", "manual",
            "漏检", "误判", "装夹", "clamping",
            "标识", "label", "记录", "record",
            "漏工序", "跳序",
        ]
        if any(kw in defect_lower for kw in man_keywords):
            evidence = [f"缺陷类型 {defect_type} 属于人员操作相关缺陷"]
            if ctx and ctx.operator_id:
                evidence.insert(0, f"关联操作者：{ctx.operator_id}")
            return RootCauseResult(
                root_cause_category="man",
                root_cause=(
                    f"缺陷类型 '{defect_type}' 可能与人员操作相关，"
                    "可能原因：操作不规范、培训不足、疲劳作业或执行偏差"
                ),
                confidence=0.55,
                matched_evidence=evidence,
                corrective_action=(
                    "建议：1) 核实操作人员培训记录；"
                    "2) 检查操作标准作业程序执行情况；"
                    "3) 加强过程巡检与互检。"
                ),
                match_source="rule_based",
            )

        # ── 3. 工序名称兜底推断 ──
        process_lower = process_step.lower()
        machining_kw = ["cnc", "加工", "machining", "铣", "车", "磨", "钻"]
        thermal_kw = ["热处理", "heat", "焊接", "weld", "铸造", "cast"]

        if any(kw in process_lower for kw in machining_kw):
            return RootCauseResult(
                root_cause_category="machine",
                root_cause=(
                    f"缺陷 '{defect_type}' 发生在机加工工序 '{process_step}'，"
                    "推测与设备精度或刀具状态相关"
                ),
                confidence=0.50,
                matched_evidence=[f"工序 {process_step} 为机加工类型"],
                corrective_action="检查加工设备精度、刀具状态及工艺参数。",
                match_source="rule_based",
            )
        if any(kw in process_lower for kw in thermal_kw):
            return RootCauseResult(
                root_cause_category="method",
                root_cause=(
                    f"缺陷 '{defect_type}' 发生在热加工工序 '{process_step}'，"
                    "推测与工艺参数控制相关"
                ),
                confidence=0.50,
                matched_evidence=[f"工序 {process_step} 为热加工类型"],
                corrective_action="检查工艺参数（温度曲线、保温时间、冷却速率）。",
                match_source="rule_based",
            )

        return RootCauseResult(
            root_cause_category="unknown",
            root_cause=f"缺陷 '{defect_type}' 在当前规则库中无法明确匹配根因类别",
            confidence=0.0,
            matched_evidence=[],
            corrective_action="建议进行详尽的 5-Why 分析，必要时开展实验室检测。",
            match_source="none",
        )

    # ── 改进建议生成 ──────────────────────────────────────────

    @staticmethod
    def generate_recommendations(
        classification: DefectClassificationResult,
        pattern: DefectPatternInfo,
        root_cause: RootCauseResult,
        failed_indicators: list[QualityIndicatorResult],
    ) -> list[RecommendationItem]:
        """基于分类、模式、根因和指标结果生成改进建议。"""
        recommendations: list[RecommendationItem] = []

        # Critical 缺陷优先处理
        if classification.critical_items:
            recommendations.append(
                RecommendationItem(
                    priority="critical",
                    target="缺陷处理",
                    action=(
                        f"立即处理 {len(classification.critical_items)} 个 Critical 缺陷: "
                        + ", ".join(classification.critical_items[:5])
                    ),
                    expected_effect="防止严重质量问题流出",
                    responsible_role="质量工程师",
                )
            )

        # 高频缺陷改进
        if pattern.high_frequency_types:
            for ft in pattern.high_frequency_types[:3]:
                recommendations.append(
                    RecommendationItem(
                        priority="major",
                        target=f"缺陷类型: {ft}",
                        action=f"对高频缺陷 '{ft}' 建立专项改进小组，开展 8D 分析",
                        expected_effect=f"降低 '{ft}' 缺陷发生率",
                        responsible_role="质量主管",
                    )
                )

        # 根因纠正措施
        if root_cause.root_cause_category != "unknown" and root_cause.corrective_action:
            recommendations.append(
                RecommendationItem(
                    priority="major",
                    target=f"根因: {root_cause.root_cause_category}",
                    action=root_cause.corrective_action,
                    expected_effect=f"从 {root_cause.root_cause_category} 维度消除缺陷根因",
                    responsible_role="生产主管",
                )
            )

        # 不合格指标纠正
        for fi in failed_indicators:
            if fi.standard_source == "none":
                recommendations.append(
                    RecommendationItem(
                        priority="major",
                        target=f"指标: {fi.metric_name}",
                        action=f"指标 {fi.metric_name} 缺少质量标准，请补充标准定义",
                        expected_effect="建立可量化的质量判定依据",
                        responsible_role="质量工程师",
                    )
                )
            elif not fi.passed:
                recommendations.append(
                    RecommendationItem(
                        priority="major",
                        target=f"指标: {fi.metric_name}",
                        action=(
                            f"指标 {fi.metric_name} 不合格（实测 {fi.measured_value}{fi.unit}，"
                            f"标准 [{fi.standard_min}, {fi.standard_max}]{fi.unit}）"
                            "，需调整工序参数或设备状态"
                        ),
                        expected_effect=f"使 {fi.metric_name} 恢复到标准范围内",
                        responsible_role="工艺工程师",
                    )
                )

        # 默认建议
        if not recommendations:
            recommendations.append(
                RecommendationItem(
                    priority="minor",
                    target="质量体系",
                    action="当前批次质量合格，保持现有质量控制和过程监控措施",
                    expected_effect="维持当前质量水平",
                    responsible_role="质量工程师",
                )
            )

        recommendations.sort(key=lambda r: SEVERITY_ORDER.get(r.priority, 99))
        return recommendations
