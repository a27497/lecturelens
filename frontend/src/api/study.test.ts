import { expect, it } from "vitest";
import { drainStudyEvents } from "./study";

it("keeps fragmented events until complete and ignores heartbeats", () => {
  const event = { sequence: 7, event_type: "tool_started", payload: { tool: "search_course_evidence" } };
  const raw = `: heartbeat\r\n\r\nid: 7\r\nevent: tool_started\r\ndata: ${JSON.stringify(event)}\r\n\r\n`;
  const split = raw.length - 3;
  const first = drainStudyEvents(raw.slice(0, split));
  expect(first.events).toEqual([]);
  expect(drainStudyEvents(first.remaining + raw.slice(split)).events).toEqual([event]);
});

it("returns ordered events and preserves incomplete tail", () => {
  const result = drainStudyEvents('data: {"sequence":1,"event_type":"run_started","payload":{}}\n\ndata: {"sequence":2');
  expect(result.events.map(e => e.sequence)).toEqual([1]);
  expect(result.remaining).toContain('"sequence":2');
});
