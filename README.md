# 🚚 Logistics Agent Tower

### Autonomous Multi-Agent Control Tower for Distribution Center (CD) Dispatch & Route Optimization
**Powered by LangGraph, Google OR-Tools (CVRPTW), Model Context Protocol (MCP 2.x), Human-in-the-Loop & PostgreSQL**

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/orchestration-LangGraph-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![Google OR-Tools](https://img.shields.io/badge/solver-Google%20OR--Tools%20(VRP)-green.svg)](https://developers.google.com/optimization)
[![MCP 2.x](https://img.shields.io/badge/protocol-MCP%202.x%20(Official)-purple.svg)](https://modelcontextprotocol.io)
[![PostgreSQL](https://img.shields.io/badge/database-PostgreSQL%2016-blue.svg)](https://www.postgresql.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## 🎯 Visão Geral & Problema de Negócio

Em grandes operações de logística e varejo (nível Mercado Livre, Ambev, DHL), despachar centenas de entregas diariamente a partir de um **Centro de Distribuição (CD)** envolve um equilíbrio complexo de restrições operacionais:
* Capacidade física e volumétrica dos veículos (peso em kg e cubagem em $m^3$);
* Controle rígido de cadeia de frio (cargas refrigeradas isoladas em veículos térmicos);
* Janelas de recebimento dos clientes (Time Windows / SLAs);
* Idiossincrasias e restrições de doca dos clientes (rampas estreitas, proibições de caminhões pesados em bairros residenciais ou litorâneos).

O **`Logistics Agent Tower`** é uma plataforma corporativa autônoma sediada no **Centro de Distribuição de Itajaí - SC** (*Rod. Antônio Heil, 1001 - KM 1 - Itaipava, Itajaí - SC*), que orquestra um esquadrão de agentes especializados para agrupar cargas, resolver a roteirização ótima e acionar supervisão humana antes da emissão do manifesto de transporte.

---

## 🏛️ Arquitetura do Sistema

```mermaid
flowchart TD
    User([Despachante / Operador de Transporte]) --> CLI["🖥️ Rich Terminal Dashboard / FastAPI"]
    
    subgraph MultiAgent["🤖 Squad Multi-Agente (LangGraph DAG)"]
        SupInit[Supervisor: Inicialização & Memória] --> Fleet[Agente de Frota & Cubagem]
        Fleet --> Route[Agente Roteirizador CVRPTW]
        Route --> Risk[Agente de SLA & Risco]
        Risk --> HITL{Human-in-the-Loop<br/><i>LangGraph interrupt()</i>}
    end

    subgraph Optimization["⚙️ Otimização Combinatória de Produção"]
        Route <--> ORTools["<b>Google OR-Tools</b><br/>Solver C++ para CVRPTW com Janelas de Tempo"]
    end

    subgraph Protocol["🔌 Protocolo Oficial MCP 2.x (Model Context Protocol)"]
        Fleet & Route <--> MCPServer["Servidor MCP WMS / TMS<br/>(Tools & Resources padronizados)"]
    end

    subgraph DataLayer["💾 Camada de Persistência Relacional"]
        MCPServer <--> DB[("<b>PostgreSQL 16 / SQLAlchemy 2.0</b><br/>Clientes, Frota, Pedidos, Regras de Doca")]
    end

    HITL -->|Sobrecarga ou Atraso Crítico| Pause[Pausa da Execução / Alerta]
    Pause -->|Decisão do Operador| Resume[Retomada via Command resume]
    Resume --> SupEnd[Supervisor: Emissão de Manifesto]
    HITL -->|Conforme| SupEnd
    SupEnd --> Manifest([Manifesto Eletrônico de Despacho Persistido])
```

---

## 🚀 Capacidades & Diferenciais Técnicos

| Pilar | Implementação Enterprise | Benefício / Por que importa |
| :--- | :--- | :--- |
| **Orquestração Multi-Agente** | **LangGraph v1.2+** com grafo acíclico direcionado (DAG), isolamento de papéis e máquina de estados tipada com Pydantic v2 | Separação limpa de responsabilidades entre frotas, roteirização e auditoria de riscos. |
| **Otimização Combinatória** | **Google OR-Tools (CVRPTW)** modelando janelas de tempo, capacidades e tempos de descarregamento | Substitui heurísticas simplórias por um solver matemático de classe mundial (usado pelo Google e Tier-1 logística). |
| **Integração de Ferramentas** | **Model Context Protocol (MCP 2.x)** com `MCPServer` oficial expondo tools e resources operacionais | Padronização aberta da indústria que permite a qualquer agente consumir o WMS/TMS de forma desacoplada. |
| **Human-in-the-Loop (HITL)** | `interrupt()` nativo do LangGraph com **Checkpointer persistente** e retomada via `Command(resume=...)` | Tolerância a falhas e governança: se houver risco de SLA ou excesso de carga, o humano é consultado antes do despacho. |
| **Memória de Longo Prazo** | Tabela relacional de regras operacionais e idiossincrasias de clientes (`customer_rules`) | O agente lembra de restrições de doca (ex: *"Bistek Fazenda só aceita VUC devido à rampa"*). |
| **Persistência Relacional** | **PostgreSQL 16** via Docker Compose + **SQLAlchemy 2.0 ORM** com tipagem estrita | Integridade referencial real, transações ACID e consultas indexadas (sem arquivos texto ou CSVs soltos). |
| **Infraestrutura em Nuvem (IaC)** | Módulos **Terraform para Google Cloud Platform (GCP)** em `infra/terraform/gcp/` | Cloud Run, Cloud SQL (PostgreSQL), Artifact Registry e BigQuery prontos para produção. |

---

## 📍 Cenário Operacional: CD Itajaí - SC

O protótipo opera com clientes e restrições geográficas reais de **Itajaí - SC e pólos adjacentes**:
* **Centro de Distribuição (Depot)**: *Rod. Antônio Heil, 1001 - KM 1 - Itaipava, Itajaí - SC* (Acesso estratégico à BR-101 e SC-486).
* **Clientes Cadastrados no Banco**:
  1. `Supermercado Bistek` (Bairro Fazenda, Itajaí) — *Restrição de rampa estreita: apenas VUC permitido*.
  2. `Komprão Koch Atacadista` (Bairro Cordeiros, Itajaí) — *Doca para Toco: fila intensa após 09:00 na Av. Reinaldo Schmithausen*.
  3. `Pescados & Frigorífico Costa Sul` (Centro / Porto, Itajaí) — *Cadeia de frio obrigatória: veículo térmico refrigerado*.
  4. `Angeloni Supermercados` (Quarta Avenida, Balneário Camboriú) — *Janela matutina para evitar congestionamento na BR-101*.
  5. `Farmácia Preço Popular` (São Vicente, Itajaí) — *Medicamentos com entrega em nível de solo*.
  6. `Armazém & Adega Brava Beach` (Praia Brava, Itajaí) — *Decreto municipal: proibido tráfego de caminhões pesados; carga de alto valor*.
  7. `Fort Atacadista` (Ressacada, Itajaí) — *Carga seca consolidada*.
  8. `Supermercado Koch` (Centro, Navegantes) — *Despacho regional*.

---

## 🛠️ Como Executar

### 1. Pré-requisitos
* Python 3.10+
* Docker & Docker Compose (opcional para subir o PostgreSQL local)

### 2. Instalação
```bash
git clone https://github.com/rodrigo85/logistics-agent-tower.git
cd logistics-agent-tower

# Instale as dependências
pip install -e ".[dev,mcp]"
pip install ortools sqlalchemy psycopg[binary]
```

### 3. Banco de Dados (PostgreSQL via Docker ou SQLite automático)
Se tiver o Docker rodando:
```bash
docker compose up -d
# O PostgreSQL estará em localhost:5432 e o Adminer em localhost:8080
```
> **Nota**: Se o Docker não estiver ativo, o sistema utiliza automaticamente a base relacional SQLite local em `data/logistics.db`, sem necessidade de nenhuma configuração adicional e com 100% das tabelas e integridade preservadas.

### 4. Executando o Painel Interativo no Terminal (CLI)
```bash
python -m logistics_tower.cli
```
O painel Rich exibirá:
1. Tabela de ocupação de peso e cubagem de cada caminhão;
2. Sequência de paradas geradas pelo **Google OR-Tools** com previsão de chegada (ETA) e checagem de SLA;
3. Alertas de conformidade;
4. **Prompt Human-in-the-Loop**: Caso detecte inconsistências, pausa a tela e solicita aprovação do operador humano (`[A]provar` ou `[R]ejeitar`).

### 5. Executando a API REST (FastAPI)
```bash
python -m logistics_tower.api.main
```
Acesse a documentação interativa Swagger em: **`http://localhost:8000/docs`**

* `POST /dispatch/plan`: Inicia o planejamento de despacho na thread; pausa com status `AWAITING_HUMAN_APPROVAL` se houver exceções operacionais.
* `POST /dispatch/resume`: Recebe a decisão e observação do despachante e finaliza a emissão do manifesto.
* `GET /mcp/tools`: Lista ferramentas expostas via Model Context Protocol.

---

## 🧪 Testes Automatizados

O projeto conta com suite de testes herméticos cobrindo todos os módulos:
```bash
pytest tests/
```
**Resultado**:
```text
tests/test_api.py ............... [ 27%]
tests/test_fleet_service.py ...... [ 36%]
tests/test_hitl_graph.py ......... [ 54%]
tests/test_mcp.py ................ [ 72%]
tests/test_memory.py ............. [ 81%]
tests/test_routing_service.py .... [100%]

======================= 11 passed in 21s =======================
```

---

## 📄 Licença
Distribuído sob licença MIT. Desenvolvido por Rodrigo Andreatta da Costa.
