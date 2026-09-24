"""
Database Seeder for Logistics Control Tower.
Populates customers, fleet, customer rules, and orders for Itajaí - SC and coastal hubs.
"""

import logging
from logistics_tower.db.models import Customer, CustomerRule, Order, Vehicle
from logistics_tower.db.session import SessionLocal, init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def seed_database():
    """Initializes schema and populates real database records."""
    init_db()
    db = SessionLocal()

    try:
        # Check if already seeded
        if db.query(Customer).count() > 0:
            logger.info("Database already contains customer data. Skipping seed.")
            return

        logger.info("Seeding customers in Itajaí - SC and surrounding hubs...")

        customers_data = [
            {
                "code": "CUST-ITJ-001",
                "name": "Supermercado Bistek - Fazenda",
                "document_cnpj": "83.261.411/0001-92",
                "address": "Rua Sete de Setembro, 1200",
                "neighborhood": "Fazenda",
                "city": "Itajaí",
                "state": "SC",
                "zip_code": "88301-202",
                "lat": -26.9185,
                "lng": -48.6492,
                "contact_phone": "(47) 3348-1000",
                "dock_type": "RAMPA_ESTREITA",
                "max_vehicle_allowed": "VUC",
                "rules": [
                    {
                        "category": "ACCESS_RESTRICTION",
                        "content": "Rua residencial e rampa de doca estreita no bairro Fazenda. Apenas veículos VUC autorizados. Proibido caminhão Truck.",
                        "priority": "CRITICAL",
                    }
                ],
            },
            {
                "code": "CUST-ITJ-002",
                "name": "Komprão Koch Atacadista - Cordeiros",
                "document_cnpj": "02.831.356/0014-50",
                "address": "Av. Reinaldo Schmithausen, 1850",
                "neighborhood": "Cordeiros",
                "city": "Itajaí",
                "state": "SC",
                "zip_code": "88310-001",
                "lat": -26.8820,
                "lng": -48.6875,
                "contact_phone": "(47) 3249-5500",
                "dock_type": "ELEVADA",
                "max_vehicle_allowed": "TOCO",
                "rules": [
                    {
                        "category": "DOCK_WINDOW",
                        "content": "Fila severa de carretas na Av. Reinaldo Schmithausen após 09:00. Priorizar descarga entre 06:00 e 08:30.",
                        "priority": "HIGH",
                    }
                ],
            },
            {
                "code": "CUST-ITJ-003",
                "name": "Pescados & Frigorífico Costa Sul - Porto",
                "document_cnpj": "04.112.980/0001-33",
                "address": "Rua Pedro Ferreira, 350",
                "neighborhood": "Centro / Porto",
                "city": "Itajaí",
                "state": "SC",
                "zip_code": "88301-030",
                "lat": -26.9070,
                "lng": -48.6540,
                "contact_phone": "(47) 3341-8200",
                "dock_type": "DOCA_FRIGORIFICADA",
                "max_vehicle_allowed": "VUC",
                "rules": [
                    {
                        "category": "COLD_CHAIN",
                        "content": "Exige controle estrito de cadeia de frio. Conferência de temperatura obrigatória antes do descarregamento na doca portuária.",
                        "priority": "CRITICAL",
                    }
                ],
            },
            {
                "code": "CUST-BC-004",
                "name": "Angeloni Supermercados - Quarta Avenida",
                "document_cnpj": "83.646.984/0022-18",
                "address": "Quarta Avenida, 880",
                "neighborhood": "Centro",
                "city": "Balneário Camboriú",
                "state": "SC",
                "zip_code": "88330-110",
                "lat": -26.9910,
                "lng": -48.6360,
                "contact_phone": "(47) 3263-4000",
                "dock_type": "SUBSOLO_LIMITADO",
                "max_vehicle_allowed": "VUC",
                "rules": [
                    {
                        "category": "TIME_WINDOW_TRAFFIC",
                        "content": "Trânsito de entrada em Balneário Camboriú complica após 08:30 pela BR-101. Agendar primeira parada da manhã.",
                        "priority": "HIGH",
                    }
                ],
            },
            {
                "code": "CUST-ITJ-005",
                "name": "Farmácia Preço Popular - São Vicente",
                "document_cnpj": "84.307.848/0055-60",
                "address": "Rua Estefano José Vanolli, 920",
                "neighborhood": "São Vicente",
                "city": "Itajaí",
                "state": "SC",
                "zip_code": "88309-000",
                "lat": -26.9045,
                "lng": -48.6935,
                "contact_phone": "(47) 3346-7788",
                "dock_type": "NIVEL_SOLO",
                "max_vehicle_allowed": "VUC",
                "rules": [],
            },
            {
                "code": "CUST-ITJ-006",
                "name": "Armazém & Adega Brava Beach",
                "document_cnpj": "31.450.890/0001-12",
                "address": "Av. José Medeiros Vieira, 1400",
                "neighborhood": "Praia Brava",
                "city": "Itajaí",
                "state": "SC",
                "zip_code": "88306-800",
                "lat": -26.9530,
                "lng": -48.6280,
                "contact_phone": "(47) 3344-9900",
                "dock_type": "LATERAL_SERVICO",
                "max_vehicle_allowed": "VUC",
                "rules": [
                    {
                        "category": "SECURITY_AND_RESTRICTION",
                        "content": "Av. da praia tem restrição diurna para caminhões pesados. Apenas VUC autorizado. Carga de alto valor (vinhos e destilados finos).",
                        "priority": "CRITICAL",
                    }
                ],
            },
            {
                "code": "CUST-ITJ-007",
                "name": "Fort Atacadista - Ressacada",
                "document_cnpj": "09.477.652/0038-70",
                "address": "Rua Tijucas, 1050",
                "neighborhood": "Ressacada",
                "city": "Itajaí",
                "state": "SC",
                "zip_code": "88307-300",
                "lat": -26.9160,
                "lng": -48.6780,
                "contact_phone": "(47) 3349-2233",
                "dock_type": "ELEVADA",
                "max_vehicle_allowed": "TOCO",
                "rules": [],
            },
            {
                "code": "CUST-NAV-008",
                "name": "Supermercado Koch - Navegantes Centro",
                "document_cnpj": "02.831.356/0008-01",
                "address": "Av. Prefeito Cirino Adolfo Cabral, 450",
                "neighborhood": "Centro",
                "city": "Navegantes",
                "state": "SC",
                "zip_code": "88370-000",
                "lat": -26.8920,
                "lng": -48.6510,
                "contact_phone": "(47) 3342-1200",
                "dock_type": "NIVEL_SOLO",
                "max_vehicle_allowed": "TOCO",
                "rules": [],
            },
        ]

        cust_obj_map = {}
        for c in customers_data:
            rules_data = c.pop("rules")
            cust = Customer(**c)
            db.add(cust)
            db.flush()
            cust_obj_map[cust.code] = cust

            for r in rules_data:
                rule = CustomerRule(
                    customer_id=cust.id,
                    rule_category=r["category"],
                    content=r["content"],
                    priority=r["priority"],
                )
                db.add(rule)

        logger.info("Seeding vehicles at CD Itajaí (Itaipava)...")
        fleet_data = [
            {
                "vehicle_id": "VEH-ITJ-VUC-01",
                "plate": "RLS7B14",
                "model": "Iveco Daily 35S14 Baú Seco (VUC)",
                "vehicle_type": "VUC",
                "max_weight_kg": 1600.0,
                "max_volume_m3": 11.0,
                "has_refrigeration": False,
                "driver_name": "Carlos Eduardo da Silva",
                "driver_phone": "(47) 99123-4567",
                "current_status": "AVAILABLE",
                "home_cd_id": "CD-ITAJAI-SC01",
            },
            {
                "vehicle_id": "VEH-ITJ-REF-02",
                "plate": "MKF9C32",
                "model": "Hyundai HR Refrigerado Termo King (VUC)",
                "vehicle_type": "VUC",
                "max_weight_kg": 1500.0,
                "max_volume_m3": 9.5,
                "has_refrigeration": True,
                "driver_name": "Marcos Vinicius Santos",
                "driver_phone": "(47) 99234-5678",
                "current_status": "AVAILABLE",
                "home_cd_id": "CD-ITAJAI-SC01",
            },
            {
                "vehicle_id": "VEH-ITJ-TOCO-03",
                "plate": "QJQ4E88",
                "model": "Mercedes-Benz Atego 1419 Baú (Toco)",
                "vehicle_type": "TOCO",
                "max_weight_kg": 6000.0,
                "max_volume_m3": 32.0,
                "has_refrigeration": False,
                "driver_name": "Roberto Almeida",
                "driver_phone": "(47) 99345-6789",
                "current_status": "AVAILABLE",
                "home_cd_id": "CD-ITAJAI-SC01",
            },
        ]
        for v in fleet_data:
            db.add(Vehicle(**v))

        logger.info("Seeding pending delivery orders for today...")
        orders_data = [
            {
                "order_number": "ORD-ITJ-2026-001",
                "customer_code": "CUST-ITJ-001",
                "cd_id": "CD-ITAJAI-SC01",
                "weight_kg": 720.0,
                "volume_m3": 3.2,
                "cargo_type": "dry",
                "window_start": "07:30",
                "window_end": "11:00",
                "priority": "VIP",
                "value_brl": 22400.0,
            },
            {
                "order_number": "ORD-ITJ-2026-002",
                "customer_code": "CUST-ITJ-002",
                "cd_id": "CD-ITAJAI-SC01",
                "weight_kg": 2800.0,
                "volume_m3": 9.4,
                "cargo_type": "dry",
                "window_start": "06:00",
                "window_end": "09:30",
                "priority": "STANDARD",
                "value_brl": 41500.0,
            },
            {
                "order_number": "ORD-ITJ-2026-003",
                "customer_code": "CUST-ITJ-003",
                "cd_id": "CD-ITAJAI-SC01",
                "weight_kg": 850.0,
                "volume_m3": 3.8,
                "cargo_type": "refrigerated",
                "window_start": "08:00",
                "window_end": "11:30",
                "priority": "VIP",
                "value_brl": 38900.0,
            },
            {
                "order_number": "ORD-ITJ-2026-004",
                "customer_code": "CUST-BC-004",
                "cd_id": "CD-ITAJAI-SC01",
                "weight_kg": 610.0,
                "volume_m3": 2.6,
                "cargo_type": "refrigerated",
                "window_start": "07:00",
                "window_end": "10:30",
                "priority": "VIP",
                "value_brl": 29800.0,
            },
            {
                "order_number": "ORD-ITJ-2026-005",
                "customer_code": "CUST-ITJ-005",
                "cd_id": "CD-ITAJAI-SC01",
                "weight_kg": 340.0,
                "volume_m3": 1.4,
                "cargo_type": "refrigerated",
                "window_start": "09:00",
                "window_end": "13:30",
                "priority": "STANDARD",
                "value_brl": 19200.0,
            },
            {
                "order_number": "ORD-ITJ-2026-006",
                "customer_code": "CUST-ITJ-006",
                "cd_id": "CD-ITAJAI-SC01",
                "weight_kg": 540.0,
                "volume_m3": 2.1,
                "cargo_type": "dry",
                "window_start": "13:00",
                "window_end": "16:30",
                "priority": "HIGH_RISK_LOAD",
                "value_brl": 86000.0,
            },
            {
                "order_number": "ORD-ITJ-2026-007",
                "customer_code": "CUST-ITJ-007",
                "cd_id": "CD-ITAJAI-SC01",
                "weight_kg": 1950.0,
                "volume_m3": 7.0,
                "cargo_type": "dry",
                "window_start": "08:30",
                "window_end": "14:00",
                "priority": "STANDARD",
                "value_brl": 35200.0,
            },
        ]

        for o in orders_data:
            c_code = o.pop("customer_code")
            cust_id = cust_obj_map[c_code].id
            order = Order(customer_id=cust_id, status="PENDING", **o)
            db.add(order)

        db.commit()
        logger.info(f"Database successfully seeded with {len(customers_data)} customers, {len(fleet_data)} vehicles, and {len(orders_data)} orders!")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to seed database: {e}")
        raise e
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
