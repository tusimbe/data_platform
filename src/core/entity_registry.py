from src.models.unified import (
    UnifiedCustomer,
    UnifiedOrder,
    UnifiedProduct,
    UnifiedInventory,
    UnifiedProject,
    UnifiedContact,
)

ENTITY_REGISTRY: dict[str, dict] = {
    "customer": {"table": "unified_customers", "model": UnifiedCustomer, "id_field": "id"},
    "order": {"table": "unified_orders", "model": UnifiedOrder, "id_field": "id"},
    "product": {"table": "unified_products", "model": UnifiedProduct, "id_field": "id"},
    "inventory": {"table": "unified_inventory", "model": UnifiedInventory, "id_field": "id"},
    "project": {"table": "unified_projects", "model": UnifiedProject, "id_field": "id"},
    "contact": {"table": "unified_contacts", "model": UnifiedContact, "id_field": "id"},
    "sales_order": {"table": "unified_orders", "model": UnifiedOrder, "id_field": "FBillNo"},
    "purchase_order": {"table": "unified_orders", "model": UnifiedOrder, "id_field": "FBillNo"},
    "material": {"table": "unified_products", "model": UnifiedProduct, "id_field": "FNumber"},
    "bom": {"table": "unified_products", "model": UnifiedProduct, "id_field": "FID"},
    "voucher": {"table": "unified_orders", "model": UnifiedOrder, "id_field": "FBillNo"},
}


def get_entity_table(entity: str) -> str:
    entry = ENTITY_REGISTRY.get(entity)
    if entry:
        return entry["table"]
    return f"unified_{entity}"


def get_entity_model(target_table: str):
    for entry in ENTITY_REGISTRY.values():
        if entry["table"] == target_table:
            return entry["model"]
    return None


def get_entity_id_field(entity: str) -> str:
    entry = ENTITY_REGISTRY.get(entity)
    if entry:
        return entry["id_field"]
    return "id"
