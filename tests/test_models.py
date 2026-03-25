from src.models.base import Base


def test_base_model_exists():
    """声明式基类应存在且可用"""
    assert Base is not None
    assert hasattr(Base, "metadata")
