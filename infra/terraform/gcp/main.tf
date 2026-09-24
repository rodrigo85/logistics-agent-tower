terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.20.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "random_password" "db_password" {
  length  = 24
  special = false
}

# --- Artifact Registry for Container Images -----------------------------------
resource "google_artifact_registry_repository" "repo" {
  location      = var.region
  repository_id = var.app_name
  description   = "Docker repository for Logistics Control Tower"
  format        = "DOCKER"
}

# --- Cloud SQL (PostgreSQL 16) ------------------------------------------------
resource "google_sql_database_instance" "postgres" {
  name             = "${var.app_name}-pg16"
  database_version = "POSTGRES_16"
  region           = var.region

  settings {
    tier = var.db_tier

    ip_configuration {
      ipv4_enabled = true # Can be private IP in VPC
    }

    backup_configuration {
      enabled = true
    }

    database_flags {
      name  = "max_connections"
      value = "200"
    }
  }

  deletion_protection = false
}

resource "google_sql_database" "database" {
  name     = var.db_name
  instance = google_sql_database_instance.postgres.name
}

resource "google_sql_user" "user" {
  name     = var.db_user
  instance = google_sql_database_instance.postgres.name
  password = random_password.db_password.result
}

# --- BigQuery for Historical Route Telemetry & SLA Analytics -------------------
resource "google_bigquery_dataset" "logistics_telemetry" {
  dataset_id  = "logistics_telemetry"
  description = "Historical route telemetry, SLA breaches, and driver shift metrics"
  location    = "southamerica-east1"
}

resource "google_bigquery_table" "route_telemetry" {
  dataset_id          = google_bigquery_dataset.logistics_telemetry.dataset_id
  table_id            = "route_telemetry_history"
  deletion_protection = false

  schema = <<EOF
[
  {"name": "manifest_id", "type": "STRING", "mode": "REQUIRED"},
  {"name": "vehicle_id", "type": "STRING", "mode": "REQUIRED"},
  {"name": "driver_name", "type": "STRING", "mode": "NULLABLE"},
  {"name": "planned_km", "type": "FLOAT", "mode": "REQUIRED"},
  {"name": "planned_duration_min", "type": "FLOAT", "mode": "REQUIRED"},
  {"name": "total_stops", "type": "INTEGER", "mode": "REQUIRED"},
  {"name": "sla_on_time_pct", "type": "FLOAT", "mode": "REQUIRED"},
  {"name": "dispatched_at", "type": "TIMESTAMP", "mode": "REQUIRED"}
]
EOF
}

# --- Secret Manager for API Keys ---------------------------------------------
resource "google_secret_manager_secret" "db_conn" {
  secret_id = "${var.app_name}-db-url"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "db_conn_version" {
  secret      = google_secret_manager_secret.db_conn.id
  secret_data = "postgresql+psycopg://${var.db_user}:${random_password.db_password.result}@${google_sql_database_instance.postgres.public_ip_address}:5432/${var.db_name}"
}

# --- Cloud Run (API & Multi-Agent Engine) --------------------------------------
resource "google_cloud_run_v2_service" "api" {
  name     = var.app_name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    scaling {
      min_instance_count = 1
      max_instance_count = 10
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.repo.name}/api:latest"

      resources {
        limits = {
          cpu    = "2"
          memory = "4Gi"
        }
      }

      env {
        name  = "ENV"
        value = "production"
      }
      env {
        name  = "DEFAULT_CD_ID"
        value = "CD-ITAJAI-SC01"
      }
      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.db_conn.secret_id
            version = "latest"
          }
        }
      }
    }
  }
}
