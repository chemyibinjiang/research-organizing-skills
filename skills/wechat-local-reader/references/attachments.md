# Attachments and Media

The bundled `map_group_attachments.py` and `decode_group_images.py` adapt the
existing local reader. Inspect their `--help` before use; do not
assume text-export arguments apply to them. Use only a selected message/group and
private output directory. They must not be pointed at writable live databases.

For resource databases, use `snapshot_db()` from `read_chat.py` with the selected
profile to snapshot `message/message_resource.db` or `hardlink/hardlink.db` only
when needed. It accepts only relative paths inside `source_root` and writes copies
under the task's private run directory.

Pass `read_chat.py`'s `messages.json` directly to `--messages-json`. Resource
matching uses server IDs or a unique local-ID/time/type composite, never a local
ID alone across shards. Ambiguous or unsupported matches remain unresolved.
Plain-file paths are candidates, not a guarantee of correct file content.

Match using message metadata, file name, source time and hashes where available.
Do not choose a similarly named local file solely because its modification time is
newer. Keep the original file unchanged. Files from private chats may require the
message's filename/cache lookup; do not falsely claim the group mapper handles all
private-chat attachments. If a matching file cannot be established, ask for it.

For images, inspect the decoded original; note if only a thumbnail was available.
The image decoder requires its existing protected image key, which is separate
from the database key. Missing/invalid image keys stop decoding; this installed
copy has no key derivation or replacement path. Ask for the image if unavailable.
Voice and video are not transcribed by the text reader. A call record cannot
establish what was agreed during the call. Report these gaps explicitly.
