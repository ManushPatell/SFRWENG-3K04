# Draft ADC integration contract

This is a proposed course interface, not a claim about a commercial cabinet protocol. Agree it with Part A before use. HTTP/JSON server listens on 127.0.0.1:8765. Real network access is deliberately not configured.

Every device request supplies `Authorization: Bearer <device credential>`; POST also uses `Content-Type: application/json`. Normal responses are 200 JSON; malformed/invalid requests 400; authentication/authorization failures 403. Bodies are limited to 1 MiB. Requests must carry the matching Host header. Shared credential is a prototype limitation: cabinets are not independently authenticated.

| Method/path | Contract |
|---|---|
| POST /api/device/register | `{ "cabinet_id": "EXTERNAL-01" }`; register identifier; idempotent |
| GET /api/device/poll?cabinet_id=EXTERNAL-01 | Returns outstanding heartbeat or null, plus queued commands only when verified |
| POST /api/device/heartbeat | cabinet_id, request_id, integer answer; answer is a+b; must arrive before deadline |
| POST /api/device/event | Envelope below; duplicate identity returns accepted=true, duplicate=true without new effects |
| POST /api/device/command-ack | cabinet_id, command_id, status=accepted or rejected; acknowledgement is receipt/acceptance, not proof of physical completion |

Event envelope:

```json
{"cabinet_id":"EXTERNAL-01","event_id":"unique-event-id","sequence":1,"timestamp":1793440000,"type":"dispense","data":{"drawer_id":"D1","pocket_id":"P1","medication_id":"EXAMPLE","quantity":1,"operator_id":"DEMO-USER","patient_id":null,"lot":null}}
```

Use current Unix seconds for timestamp, a never-reused event ID and strictly increasing integer sequence per cabinet. Persist sequence across reconnects/restarts. The timestamp above illustrates structure only. Types: inventory (locations array), dispense/restock (transaction), health, maintenance, alarm. See tools/device_client.py for complete current inventory and health payloads. maintenance requires activity and operator_id. alarm requires kind (device_failure, unsafe_state or discrepancy), condition and message.

Inventory fields: drawer_id, pocket_id, medication_id, name, din, strength, dosage_form, integer quantity, full_stock, threshold, threshold_type (quantity/percent), optional lot. Inventory snapshots update included locations; location deletion/reassignment and multi-lot quantities are not supported. Product metadata consistency is enforced for matching medication IDs.

Health requires operational_status=operational/maintenance/fault; power/hardware/sensors/backup/cooling each ok/failed/unsupported/unknown; nonnegative uptime; Boolean unsafe. The ADC decides whether a door/interlock condition is unsafe; HMS does not infer hardware timing from raw sensors.

On disconnect, retained records remain accessible; commands are withheld until verification. No queued command expiry/retry policy or durable remote completion guarantee is provided. Rejected out-of-order events require reconciliation by the sender; known sequence gaps mark historical reconstruction incomplete. No automatic retransmission or sequence reset negotiation is implemented.
