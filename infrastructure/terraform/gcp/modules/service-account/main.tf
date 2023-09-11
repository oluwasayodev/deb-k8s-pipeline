resource "google_service_account" "service_account" {
  account_id = var.service_account_id
  description = "A service account for managing access and permissions"
}