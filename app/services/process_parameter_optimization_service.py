from __future__ import annotations

from app.schemas.process_parameter_optimization import (
    ConstraintViolation,
    CorrelationTrend,
    CurrentParameter,
    HistoricalBatch,
    ImprovementEstimate,
    OptimizeFor,
    ParameterConstraint,
    ParameterCorrelation,
    ParameterRecommendation,
    ProcessInfo,
    QualityFeedback,
)


class ProcessParameterOptimizationService:
    """工艺参数优化核心业务服务。

    所有方法均为纯规则计算，不访问数据库、模型 API 或外部网络。
    """

    # ── RAG 预留接口 ──────────────────────────────────────────

    @staticmethod
    def match_process_history(
        process_id: str,
        product_id: str,
        historical_batches: list[HistoricalBatch],
    ) -> list[HistoricalBatch]:
        """RAG 预留：按工艺/产品匹配历史批次。

        当前返回全部传入批次。后续可替换为向量检索。
        """
        return [
            b
            for b in historical_batches
            if process_id or product_id  # 当前不过滤
        ] or historical_batches

    @staticmethod
    def match_parameter_constraints(
        process_id: str,
        constraints: list[ParameterConstraint],
    ) -> list[ParameterConstraint]:
        """RAG 预留：按工艺匹配参数约束。

        当前返回全部传入约束。后续可替换为向量检索。
        """
        return constraints

    @staticmethod
    def match_quality_feedback(
        batch_id: str,
        feedbacks: list[QualityFeedback],
    ) -> list[QualityFeedback]:
        """RAG 预留：按批次匹配质量反馈。

        当前按 batch_id 精确匹配。后续可替换为语义检索。
        """
        return [f for f in feedbacks if f.batch_id == batch_id]

    # ── 批次校验 ──────────────────────────────────────────────

    @staticmethod
    def validate_batch_count(
        batches: list[HistoricalBatch],
    ) -> tuple[bool, str]:
        """校验历史批次数量是否充足。"""
        if len(batches) < 3:
            return False, f"历史批次数据不足：{len(batches)} 条（最少需要 3 条）"
        return True, f"历史批次数据充足：{len(batches)} 条"

    # ── 参数约束检查 ──────────────────────────────────────────

    @staticmethod
    def check_parameter_constraints(
        current_params: list[CurrentParameter],
        constraints: list[ParameterConstraint],
    ) -> list[ConstraintViolation]:
        """检查当前参数是否在约束范围内。"""
        constraint_map = {c.parameter_name: c for c in constraints}
        violations: list[ConstraintViolation] = []

        for cp in current_params:
            c = constraint_map.get(cp.parameter_name)
            if c is None:
                continue
            if cp.value < c.min_value:
                violations.append(
                    ConstraintViolation(
                        parameter_name=cp.parameter_name,
                        current_value=cp.value,
                        min_value=c.min_value,
                        max_value=c.max_value,
                        safety_critical=c.safety_critical,
                        violation_type="below_min",
                    )
                )
            elif cp.value > c.max_value:
                violations.append(
                    ConstraintViolation(
                        parameter_name=cp.parameter_name,
                        current_value=cp.value,
                        min_value=c.min_value,
                        max_value=c.max_value,
                        safety_critical=c.safety_critical,
                        violation_type="above_max",
                    )
                )

        return violations

    @staticmethod
    def has_safety_critical_violation(
        violations: list[ConstraintViolation],
    ) -> bool:
        """是否存在安全关键参数违规。"""
        return any(v.safety_critical for v in violations)

    # ── 质量目标判断 ──────────────────────────────────────────

    @staticmethod
    def analyze_quality_targets(
        batches: list[HistoricalBatch],
        min_yield_rate: float,
        max_defect_rate: float,
        target_cycle_time: float,
    ) -> tuple[bool, bool, bool, list[HistoricalBatch]]:
        """分析批次是否满足质量 + 效率目标。

        Returns:
            has_quality_batch: 存在满足良品率+缺陷率目标的批次
            has_efficient_batch: 存在满足节拍目标的批次
            has_joint_batch: 存在同时满足质量和效率目标的批次
            joint_batches: 同时满足的批次列表
        """
        has_quality_batch = False
        has_efficient_batch = False
        joint_batches: list[HistoricalBatch] = []

        for b in batches:
            quality_ok = (
                b.yield_rate >= min_yield_rate and b.defect_rate <= max_defect_rate
            )
            efficient_ok = (
                target_cycle_time <= 0 or b.cycle_time_minutes <= target_cycle_time
            )

            if quality_ok:
                has_quality_batch = True
            if efficient_ok:
                has_efficient_batch = True
            if quality_ok and efficient_ok:
                joint_batches.append(b)

        has_joint_batch = len(joint_batches) > 0
        return has_quality_batch, has_efficient_batch, has_joint_batch, joint_batches

    @staticmethod
    def check_conflicting_targets(
        batches: list[HistoricalBatch],
        min_yield_rate: float,
        max_defect_rate: float,
        target_cycle_time: float,
    ) -> bool:
        """检测质量目标与效率目标是否冲突。

        冲突定义：存在满足质量的批次、存在满足效率的批次，
        但没有同时满足两者的批次。
        """
        if len(batches) == 0:
            return False
        has_q, has_e, has_joint, _ = (
            ProcessParameterOptimizationService.analyze_quality_targets(
                batches, min_yield_rate, max_defect_rate, target_cycle_time
            )
        )
        return has_q and has_e and not has_joint

    # ── 质量风险检测 ──────────────────────────────────────────

    @staticmethod
    def assess_quality_risk(
        batches: list[HistoricalBatch],
        min_yield_rate: float,
        max_defect_rate: float,
    ) -> tuple[bool, float, float]:
        """评估当前/历史质量是否低于目标。

        Returns:
            at_risk: 是否存在质量风险
            avg_yield: 历史平均良品率
            avg_defect: 历史平均缺陷率
        """
        if not batches:
            return True, 0.0, 0.0

        avg_yield = sum(b.yield_rate for b in batches) / len(batches)
        avg_defect = sum(b.defect_rate for b in batches) / len(batches)
        at_risk = avg_yield < min_yield_rate or avg_defect > max_defect_rate
        return at_risk, avg_yield, avg_defect

    # ── 参数-质量相关性分析 ────────────────────────────────────

    @staticmethod
    def correlate_parameters_with_quality(
        batches: list[HistoricalBatch],
    ) -> list[ParameterCorrelation]:
        """对每个参数分析其与质量的相关性趋势。

        方法：按参数值中位数分为高值组和低值组，比较两组的平均表现。
        """
        if len(batches) < 2:
            return []

        # 收集所有参数名
        param_names: set[str] = set()
        for b in batches:
            param_names.update(b.parameters.keys())

        correlations: list[ParameterCorrelation] = []

        for pname in sorted(param_names):
            # 按该参数值排序
            valid_batches = [b for b in batches if pname in b.parameters]
            if len(valid_batches) < 2:
                continue

            sorted_batches = sorted(valid_batches, key=lambda b: b.parameters[pname])
            mid = len(sorted_batches) // 2
            low_group = sorted_batches[:mid]
            high_group = sorted_batches[mid:]

            if not low_group or not high_group:
                continue

            low_avg_yield = sum(b.yield_rate for b in low_group) / len(low_group)
            high_avg_yield = sum(b.yield_rate for b in high_group) / len(high_group)
            low_avg_defect = sum(b.defect_rate for b in low_group) / len(low_group)
            high_avg_defect = sum(b.defect_rate for b in high_group) / len(high_group)
            low_avg_cycle = sum(b.cycle_time_minutes for b in low_group) / len(low_group)
            high_avg_cycle = (
                sum(b.cycle_time_minutes for b in high_group) / len(high_group)
            )

            # 趋势判断
            yield_better = high_avg_yield > low_avg_yield
            defect_better = high_avg_defect < low_avg_defect
            quality_better = yield_better and defect_better
            cycle_worse = high_avg_cycle > low_avg_cycle

            if quality_better and not cycle_worse:
                trend: CorrelationTrend = "positive_quality_correlation"
                desc = f"参数 {pname} 高值组良品率更高、缺陷率更低，且效率未恶化"
            elif quality_better and cycle_worse:
                trend = "efficiency_tradeoff"
                desc = f"参数 {pname} 高值组质量更好但节拍更长，存在质量-效率权衡"
            elif not quality_better and (high_avg_yield < low_avg_yield or high_avg_defect > low_avg_defect):
                trend = "negative_quality_correlation"
                desc = f"参数 {pname} 高值组质量表现更差"
            else:
                trend = "neutral"
                desc = f"参数 {pname} 与质量无明显线性趋势"

            correlations.append(
                ParameterCorrelation(
                    parameter_name=pname,
                    trend=trend,
                    description=desc,
                    high_group_avg_yield=round(high_avg_yield, 4),
                    low_group_avg_yield=round(low_avg_yield, 4),
                    high_group_avg_defect=round(high_avg_defect, 4),
                    low_group_avg_defect=round(low_avg_defect, 4),
                )
            )

        return correlations

    # ── 最佳批次选择 ──────────────────────────────────────────

    @staticmethod
    def select_best_batch(
        batches: list[HistoricalBatch],
        optimize_for: OptimizeFor,
    ) -> tuple[HistoricalBatch | None, float]:
        """根据优化目标选择最佳批次。

        评分规则：
          quality_first: yield_rate - defect_rate - dimension_deviation
          efficiency_first: -cycle_time + throughput (归一化)
          balanced: yield_rate + (1-defect_rate) - norm_cycle + norm_throughput
        """
        if not batches:
            return None, 0.0

        if optimize_for == "quality_first":

            def quality_score(b: HistoricalBatch) -> float:
                return (
                    b.yield_rate * 0.5
                    + (1.0 - b.defect_rate) * 0.3
                    + max(0.0, 1.0 - b.dimension_deviation) * 0.2
                )

            scored = [(b, quality_score(b)) for b in batches]

        elif optimize_for == "efficiency_first":
            max_throughput = max(b.throughput_per_hour for b in batches) or 1.0
            max_cycle = max(b.cycle_time_minutes for b in batches) or 1.0

            def efficiency_score(b: HistoricalBatch) -> float:
                norm_throughput = b.throughput_per_hour / max_throughput
                norm_cycle = 1.0 - (b.cycle_time_minutes / max_cycle) if max_cycle > 0 else 1.0
                return norm_cycle * 0.5 + norm_throughput * 0.5

            scored = [(b, efficiency_score(b)) for b in batches]

        else:  # balanced
            max_throughput = max(b.throughput_per_hour for b in batches) or 1.0
            max_cycle = max(b.cycle_time_minutes for b in batches) or 1.0

            def balanced_score(b: HistoricalBatch) -> float:
                norm_throughput = b.throughput_per_hour / max_throughput
                norm_cycle = 1.0 - (b.cycle_time_minutes / max_cycle) if max_cycle > 0 else 1.0
                return (
                    b.yield_rate * 0.35
                    + (1.0 - b.defect_rate) * 0.25
                    + norm_cycle * 0.2
                    + norm_throughput * 0.2
                )

            scored = [(b, balanced_score(b)) for b in batches]

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[0][0], round(scored[0][1], 4)

    # ── 推荐参数生成 ──────────────────────────────────────────

    @staticmethod
    def generate_recommendations(
        current_params: list[CurrentParameter],
        best_batch: HistoricalBatch | None,
        constraints: list[ParameterConstraint],
    ) -> list[ParameterRecommendation]:
        """从最佳批次生成推荐参数，并 clamp 到约束范围。"""
        constraint_map = {c.parameter_name: c for c in constraints}
        current_map = {cp.parameter_name: cp.value for cp in current_params}
        recommendations: list[ParameterRecommendation] = []

        if best_batch is None:
            return recommendations

        for pname, rec_value in best_batch.parameters.items():
            current_val = current_map.get(pname, rec_value)
            clamped = False

            c = constraint_map.get(pname)
            if c is not None:
                if rec_value < c.min_value:
                    rec_value = c.min_value
                    clamped = True
                elif rec_value > c.max_value:
                    rec_value = c.max_value
                    clamped = True

            recommendations.append(
                ParameterRecommendation(
                    parameter_name=pname,
                    current_value=current_val,
                    recommended_value=rec_value,
                    delta=round(rec_value - current_val, 2),
                    unit=c.unit if c else "",
                    clamped=clamped,
                )
            )

        return recommendations

    # ── 预期改进计算 ──────────────────────────────────────────

    @staticmethod
    def compute_expected_improvements(
        best_batch: HistoricalBatch | None,
        all_batches: list[HistoricalBatch],
    ) -> ImprovementEstimate:
        """对比最佳批次与历史平均，估算预期改进。"""
        if not all_batches or best_batch is None:
            return ImprovementEstimate(description="数据不足，无法估算改进")

        avg_yield = sum(b.yield_rate for b in all_batches) / len(all_batches)
        avg_defect = sum(b.defect_rate for b in all_batches) / len(all_batches)
        avg_cycle = sum(b.cycle_time_minutes for b in all_batches) / len(all_batches)

        yield_delta = round(best_batch.yield_rate - avg_yield, 4)
        defect_delta = round(best_batch.defect_rate - avg_defect, 4)
        cycle_delta = round(best_batch.cycle_time_minutes - avg_cycle, 2)

        desc_parts: list[str] = []
        if yield_delta > 0:
            desc_parts.append(f"良品率预计提升 {yield_delta:.2%}")
        if defect_delta < 0:
            desc_parts.append(f"缺陷率预计降低 {abs(defect_delta):.2%}")
        if cycle_delta < 0:
            desc_parts.append(f"节拍预计缩短 {abs(cycle_delta):.1f} 分钟")

        return ImprovementEstimate(
            expected_yield_rate_delta=yield_delta,
            expected_defect_rate_delta=defect_delta,
            expected_cycle_time_delta=cycle_delta,
            description="；".join(desc_parts) if desc_parts else "预期无明显改进",
        )

    # ── 当前参数是否接近最优 ──────────────────────────────────

    @staticmethod
    def is_current_near_optimal(
        current_params: list[CurrentParameter],
        best_batch: HistoricalBatch | None,
        tolerance: float = 0.05,
    ) -> bool:
        """判断当前参数是否接近最佳批次参数（相对差异 < tolerance）。"""
        if best_batch is None:
            return False

        current_map = {cp.parameter_name: cp.value for cp in current_params}
        if not current_map:
            return False

        matched = 0
        close = 0
        for pname, best_val in best_batch.parameters.items():
            if pname in current_map:
                matched += 1
                cur = current_map[pname]
                if best_val != 0 and abs(cur - best_val) / abs(best_val) < tolerance:
                    close += 1
                elif best_val == 0 and abs(cur) < 0.001:
                    close += 1

        if matched == 0:
            return False
        return (close / matched) >= 0.7  # 70% 参数接近
