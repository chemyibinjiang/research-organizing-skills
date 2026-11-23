---
name: conference-programme-check
description: Check conference schedules for chair, speaker, room, interview, tour and transport conflicts using explicit time intervals and transfer buffers. Use for proposed timetable changes or route simulations; report conflicts without silently rewriting an organizer-owned agenda.
---

# Conference Programme Check

## Build the Right Timetable

Find the approved programme and later authorized amendments. Keep a working
schedule separate from the publisher/organizer's printed agenda. A request to
review the agenda is not permission to change their master document.

Record local date, timezone, start/end, venue, participant IDs, chair, required
staff/resources, confirmation source and any setup/transfer buffer. A speaker's
talk, chair duty, interview, award presentation and travel are separate events.
Hotel booking dates alone do not prove availability.

Use [the interval schema](references/schedule-schema.md) and
`scripts/check_schedule.py` for explicit resource overlaps and unknown times.
Treat a clean result only as no conflicts among the encoded constraints.

## Model Transitions

- Include walking, loading, head counts, security, road travel and equipment tests
  where they matter. Label estimates and their source; do not make up minute-level
  availability from an arrival time or assume flight arrival equals hotel arrival.
- Use measured route timings when available. For two subgroups swapping rooms,
  model each group's walk and visit separately. A shared staircase or corridor is
  a resource; encode its occupancy if opposing flows matter. Waiting space is not
  unlimited capacity. Do not add artificial waits if the organizer allows overlap.
- For buses, distinguish hotel departure, campus arrival, tour start, return
  boarding and hotel return. Count staff and escorts in capacity and verify
  whether the driver's seat is included in the stated limit.
- Check alternatives against the same constraints: delayed arrival, simultaneous
  batches, one guest leaving early, chair replacement. Label the fallback decision
  owner rather than claiming the alternative is approved.

## Review Human Conflicts

An interval checker cannot infer every constraint. Check these explicitly:

- Is a chair introducing themselves, missing their own presentation, or assigned
  elsewhere? If a replacement is authorized, keep talk times unchanged unless asked.
- Does an interview overlap a plenary talk, meal duty or onward transport? Record
  invited / accepted / declined / needs rescheduling separately. Check assistant-
  mediated consent and topics/language when applicable.
- Do ceremony scripts, seating, awards and participant arrival/departure agree?
  A person can attend a conference but miss its opening or closing ceremony.
- Does an absent speaker leave a gap or trigger immediate continuation? Use the
  organizer's explicit policy; do not compress all subsequent slots automatically.

## Return a Decision-ready Result

Provide a proposed timetable or compact bar chart, assumptions, conflicts,
unresolved times, proposed remedy and person who must confirm it. Preserve the
user's current slide/order edits. Once a change is authorized, list affected
chairs, speakers, logistics contacts and artifacts; track notifications separately.
