from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class FieldMappingService:
    """字段映射转换服务：在外部系统字段和统一模型字段之间进行转换"""

    def apply_mappings(
        self,
        source: dict,
        mappings: list[dict],
        target_model=None,
    ) -> dict:
        """正向映射：外部系统字段 → 统一模型字段

        当 mappings 为空且提供了 target_model 时，自动将源数据中与
        目标模型列名匹配的字段直接透传（auto-passthrough）。
        """
        if mappings:
            return self._apply_explicit_mappings(source, mappings)

        if target_model is not None:
            return self._auto_passthrough(source, target_model)

        return {}

    def _apply_explicit_mappings(self, source: dict, mappings: list[dict]) -> dict:
        """使用显式映射规则转换字段"""
        result = {}
        for m in mappings:
            source_field = m["source_field"]
            target_field = m["target_field"]
            transform = m.get("transform")
            transform_config = m.get("transform_config", {})

            raw_value = source.get(source_field)

            if transform and raw_value is not None:
                raw_value = self._apply_transform(raw_value, transform, transform_config, source)

            result[target_field] = raw_value

        return result

    @staticmethod
    def _auto_passthrough(source: dict, target_model) -> dict:
        """自动透传：将源字段中与目标模型列名匹配的字段直接映射。

        跳过系统管理的列（id, source_system, external_id 等），
        只映射业务字段。
        """
        SYSTEM_COLUMNS = {
            "id",
            "source_system",
            "external_id",
            "source_data_id",
            "synced_at",
            "created_at",
            "updated_at",
        }
        valid_cols = {c.name for c in target_model.__table__.columns} - SYSTEM_COLUMNS

        result = {}
        for col in valid_cols:
            if col in source:
                value = source[col]
                # 跳过嵌套对象/列表 — 只透传标量值
                if not isinstance(value, (dict, list)):
                    result[col] = value

        return result

    def reverse_mappings(self, unified: dict, mappings: list[dict]) -> dict:
        """反向映射：统一模型字段 → 外部系统字段"""
        result = {}
        for m in mappings:
            source_field = m["source_field"]  # 外部系统字段名
            target_field = m["target_field"]  # 统一模型字段名
            value = unified.get(target_field)
            if value is not None:
                result[source_field] = value
        return result

    def _apply_transform(self, value, transform: str, config: dict, source: dict):
        """应用转换规则"""
        if transform == "date_format":
            return self._transform_date_format(value, config)
        elif transform == "value_map":
            return self._transform_value_map(value, config)
        elif transform == "concat":
            return self._transform_concat(value, config, source)
        elif transform == "split":
            return self._transform_split(value, config)
        else:
            logger.warning(f"未知的转换类型: {transform}")
            return value

    @staticmethod
    def _transform_date_format(value: str, config: dict) -> str:
        input_fmt = config.get("input", "%Y-%m-%d")
        output_fmt = config.get("output", "%Y-%m-%d")
        dt = datetime.strptime(value, input_fmt)
        return dt.strftime(output_fmt)

    @staticmethod
    def _transform_value_map(value, config: dict):
        mapping = config.get("map", {})
        return mapping.get(str(value), value)

    @staticmethod
    def _transform_concat(value, config: dict, source: dict) -> str:
        fields = config.get("fields", [])
        separator = config.get("separator", "")
        parts = [str(source.get(f, "")) for f in fields]
        return separator.join(parts)

    @staticmethod
    def _transform_split(value: str, config: dict):
        separator = config.get("separator", ",")
        index = config.get("index", 0)
        parts = value.split(separator)
        return parts[index] if index < len(parts) else value
