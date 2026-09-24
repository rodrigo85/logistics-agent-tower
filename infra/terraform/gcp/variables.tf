variable "project_id" {
  description = "GCP Project ID"
  type        = string
  default     = "logistics-tower-prod"
}

variable "region" {
  description = "Primary GCP Region for South America"
  type        = string
  default     = "southamerica-east1" # São Paulo
}

variable "app_name" {
  description = "Application name"
  type        = string
  default     = "logistics-agent-tower"
}

variable "db_tier" {
  description = "Cloud SQL machine tier"
  type        = string
  default     = "db-custom-2-7680"
}

variable "db_name" {
  description = "Database name"
  type        = string
  default     = "logistics"
}

variable "db_user" {
  description = "Database user"
  type        = string
  default     = "logistics_admin"
}
