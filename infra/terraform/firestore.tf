# Two databases so IAM can separate them: server-side Firestore access is granted
# per database, never per collection.
#   channel: customers, WhatsApp links, sessions, link tokens, deliveries (main-worker, link-web)
#   shop:    accounts, orders, payments, manual reviews (mcp-shop only)

locals {
  firestore_databases = toset(["channel", "shop"])
}

resource "google_firestore_database" "this" {
  for_each = local.firestore_databases

  name        = each.value
  location_id = var.region
  type        = "FIRESTORE_NATIVE"

  concurrency_mode            = "OPTIMISTIC"
  app_engine_integration_mode = "DISABLED"

  # Orders and payments are the system of record: refuse accidental deletes.
  delete_protection_state = "DELETE_PROTECTION_ENABLED"
  deletion_policy         = "DELETE"

  depends_on = [google_project_service.this]
}

# Composite indexes for the multi-field queries the services run.
locals {
  firestore_indexes = {
    # mcp-shop: a customer's open orders (ledger) and its order_created outbox.
    "shop-orders-customer-status"          = { database = "shop", collection = "orders", fields = ["customer_id", "status"] }
    "shop-orders-customer-event-published" = { database = "shop", collection = "orders", fields = ["customer_id", "event_published"] }
    # main-worker: deliveries waiting for the customer to reopen the 24 h window.
    "channel-deliveries-wa-id-status" = { database = "channel", collection = "deliveries", fields = ["wa_id", "status"] }
  }
}

resource "google_firestore_index" "this" {
  for_each = local.firestore_indexes

  database   = google_firestore_database.this[each.value.database].name
  collection = each.value.collection

  dynamic "fields" {
    for_each = each.value.fields
    content {
      field_path = fields.value
      order      = "ASCENDING"
    }
  }
}
