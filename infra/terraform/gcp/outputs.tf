output "cloud_run_url" {
  description = "Public URL of the deployed Logistics Control Tower API on Cloud Run"
  value       = google_cloud_run_v2_service.api.uri
}

output "cloud_sql_ip" {
  description = "Public IP address of Cloud SQL PostgreSQL instance"
  value       = google_sql_database_instance.postgres.public_ip_address
}

output "bigquery_dataset_id" {
  description = "BigQuery dataset ID for route telemetry"
  value       = google_bigquery_dataset.logistics_telemetry.dataset_id
}
