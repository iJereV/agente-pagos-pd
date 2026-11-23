# Event topics, each with a dead-letter topic. Delivery is at least once, so every
# consumer is idempotent (docs/contracts.md).

locals {
  topics = toset(["wa-inbound", "order-created", "order-ready"])

  # Push subscriptions: topic -> receiving service and path.
  push_subscriptions = {
    "wa-inbound-main-worker" = {
      topic        = "wa-inbound"
      service      = "main-worker"
      path         = "/pubsub/wa-inbound"
      ack_deadline = 300 # one agent turn
    }
    "order-ready-main-worker" = {
      topic        = "order-ready"
      service      = "main-worker"
      path         = "/pubsub/order-ready"
      ack_deadline = 300 # one delivery turn plus image upload
    }
    "order-created-image-generator" = {
      topic        = "order-created"
      service      = "image-generator"
      path         = "/pubsub/order-created"
      ack_deadline = 600 # several image generations
    }
  }

  pubsub_service_agent = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_pubsub_topic" "this" {
  for_each = local.topics

  name = each.value

  depends_on = [google_project_service.this]
}

resource "google_pubsub_topic" "dead_letter" {
  for_each = local.topics

  name = "${each.value}-dlq"

  depends_on = [google_project_service.this]
}

# Pull subscriptions keep dead-lettered messages for inspection; without one they are dropped.
resource "google_pubsub_subscription" "dead_letter" {
  for_each = local.topics

  name  = "${each.value}-dlq-inspect"
  topic = google_pubsub_topic.dead_letter[each.value].id

  message_retention_duration = "604800s"
  ack_deadline_seconds       = 60

  expiration_policy {
    ttl = ""
  }
}

resource "google_pubsub_subscription" "push" {
  for_each = local.push_subscriptions

  name  = each.key
  topic = google_pubsub_topic.this[each.value.topic].id

  ack_deadline_seconds       = each.value.ack_deadline
  message_retention_duration = "86400s"

  push_config {
    push_endpoint = "${google_cloud_run_v2_service.this[each.value.service].uri}${each.value.path}"

    oidc_token {
      service_account_email = local.sa["sa-pubsub-push"]
      audience              = google_cloud_run_v2_service.this[each.value.service].uri
    }
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dead_letter[each.value.topic].id
    max_delivery_attempts = 5
  }

  expiration_policy {
    ttl = ""
  }

  depends_on = [
    google_cloud_run_v2_service_iam_member.pubsub_push_invoker,
    google_pubsub_topic_iam_member.dead_letter_publisher,
  ]
}

# Dead lettering: the Pub/Sub service agent must publish to the DLQ topic and
# subscribe (ack) on the source subscription.
resource "google_pubsub_topic_iam_member" "dead_letter_publisher" {
  for_each = local.topics

  topic  = google_pubsub_topic.dead_letter[each.value].id
  role   = "roles/pubsub.publisher"
  member = local.pubsub_service_agent
}

resource "google_pubsub_subscription_iam_member" "dead_letter_subscriber" {
  for_each = local.push_subscriptions

  subscription = google_pubsub_subscription.push[each.key].id
  role         = "roles/pubsub.subscriber"
  member       = local.pubsub_service_agent
}
