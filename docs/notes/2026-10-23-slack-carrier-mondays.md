# Slack thread, #carrier-integration, 23 October

**Arjun:** Monday morning the carrier took 9 to 10 seconds on bookings. Our timeout is 8.
**Meera:** their guide says 5 seconds is typical, I can ask them.
**Arjun:** I added the attempt wrapper so chats do not die. Up to 2 more tries.
**Kabir:** I saw `tool_timeout` events last week, mostly Monday.
**Meera:** carrier desk says they will look at it "next sprint".
**Arjun:** should we raise our timeout to 12? Not now, 8 is what the sim uses.
