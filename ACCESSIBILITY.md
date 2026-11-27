# Accessibility

The web map should be usable by keyboard, with a screen reader and on a phone. This page states what has been
built and checked, what is known not to work, and how to report a barrier.

## What the map provides

- **Every record is reachable without a mouse.** Map points cannot be reached with Tab, so the **Records** list
  offers every changed record as a button, with search; choosing one opens its details and moves the map to it.
- **Change types are shown by shape and colour together**, so colour is never the only cue.
- **Keyboard controls:** the view switch is a radio group; the before/after divider is a slider (arrow keys,
  Home, End); panels close with Escape; focus is visible on every control; skip links lead to the filters and open
  the records list.
- **Status changes are announced:** the releases line, the release-history status and the playback position use
  live regions.
- **Reduced motion:** when the system asks for reduced motion, map transitions jump instead of easing, and history
  playback steps without animation.
- **Phones:** the filters and legend move to a bottom sheet; the main controls have touch targets of at least 44 px.

## How it has been checked

Automated browser checks at desktop (1440 × 900) and phone (390 × 844) sizes, including touch, with no console
errors; the divider's keyboard controls (arrow keys, Home, End) were tested in those checks.

## Known limitations

- **Not yet tested with a screen reader or on a real phone**: only in a desktop browser emulating a phone.
- **The basemap's own labels** (street names) come from a third-party style and are not announced.
- **The release-history playback** is visual; the record panel lists a record's positions by release as text.
- **The dark theme's overall contrast and colour balance** have not had a dedicated review yet.

## Reporting a barrier

Open an issue describing what you were trying to do, the device and browser or assistive technology, and what got
in the way. Barriers are treated as bugs.
