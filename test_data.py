
import uuid

message_id = str(uuid.uuid4())
batch_id = str(uuid.uuid4())

batch = {
    "batchId": batch_id,
    "policyRevision": "test-policy-1",
    "packages": [
        {
            "packageId": "test-package-001",
            "documents": [
                {
                    "type": "invoice",
                    "text": (
                        "Invoice from Acme Supplies. Invoice number INV-001. "
                        "Amount INR 1,000.00. [INV-001]"
                    ),
                },
                {
                    "type": "reconciliation",
                    "text": (
                        "The invoice matches the purchase order and goods "
                        "receipt. The amount is within the autonomous "
                        "approval limit. [MATCH-001]"
                    ),
                },
                {
                    "type": "payment_status",
                    "text": (
                        "No previous payment was found for this commercial "
                        "invoice. [PAY-001]"
                    ),
                },
            ],
        }
    ],
}

request_body = {
    "message": {
        "messageId": message_id,
        "contextId": str(uuid.uuid4()),
        "role": "ROLE_USER",
        "parts": [
            {
                "mediaType": "application/vnd.ga5.invoice-claim-batch+json",
                "data": batch,
            }
        ],
    },
    "configuration": {
        "returnImmediately": False,
        "historyLength": 20,
        "acceptedOutputModes": [
            "application/vnd.ga5.invoice-action-proposals+json",
            "application/vnd.ga5.invoice-action-receipts+json",
        ],
    },
}
