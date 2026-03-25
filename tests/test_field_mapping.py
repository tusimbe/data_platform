# tests/test_field_mapping.py
import pytest
from src.services.field_mapping_service import FieldMappingService


@pytest.fixture
def mapping_service():
    return FieldMappingService()


def test_simple_field_mapping(mapping_service):
    """简单字段映射：字段重命名"""
    mappings = [
        {"source_field": "FBillNo", "target_field": "order_number", "transform": None},
        {"source_field": "FDate", "target_field": "order_date", "transform": None},
        {"source_field": "FAmount", "target_field": "total_amount", "transform": None},
    ]
    source = {"FBillNo": "SO-001", "FDate": "2026-01-15", "FAmount": 1000.50}
    result = mapping_service.apply_mappings(source, mappings)
    assert result == {
        "order_number": "SO-001",
        "order_date": "2026-01-15",
        "total_amount": 1000.50,
    }


def test_date_format_transform(mapping_service):
    """日期格式转换"""
    mappings = [
        {
            "source_field": "FDate",
            "target_field": "order_date",
            "transform": "date_format",
            "transform_config": {"input": "%Y-%m-%dT%H:%M:%S", "output": "%Y-%m-%d"},
        },
    ]
    source = {"FDate": "2026-01-15T10:30:00"}
    result = mapping_service.apply_mappings(source, mappings)
    assert result["order_date"] == "2026-01-15"


def test_value_map_transform(mapping_service):
    """值映射转换"""
    mappings = [
        {
            "source_field": "FStatus",
            "target_field": "status",
            "transform": "value_map",
            "transform_config": {"map": {"A": "approved", "B": "pending", "C": "rejected"}},
        },
    ]
    source = {"FStatus": "A"}
    result = mapping_service.apply_mappings(source, mappings)
    assert result["status"] == "approved"


def test_concat_transform(mapping_service):
    """拼接转换"""
    mappings = [
        {
            "source_field": "FFirstName",
            "target_field": "name",
            "transform": "concat",
            "transform_config": {"fields": ["FFirstName", "FLastName"], "separator": " "},
        },
    ]
    source = {"FFirstName": "张", "FLastName": "三"}
    result = mapping_service.apply_mappings(source, mappings)
    assert result["name"] == "张 三"


def test_missing_source_field(mapping_service):
    """源字段不存在时应设为 None"""
    mappings = [
        {"source_field": "FMissing", "target_field": "value", "transform": None},
    ]
    source = {"FOther": "data"}
    result = mapping_service.apply_mappings(source, mappings)
    assert result["value"] is None


def test_reverse_mapping(mapping_service):
    """反向映射：统一字段 → 外部系统字段"""
    mappings = [
        {"source_field": "FBillNo", "target_field": "order_number", "transform": None},
        {"source_field": "FAmount", "target_field": "total_amount", "transform": None},
    ]
    unified = {"order_number": "SO-001", "total_amount": 2000}
    result = mapping_service.reverse_mappings(unified, mappings)
    assert result == {"FBillNo": "SO-001", "FAmount": 2000}
