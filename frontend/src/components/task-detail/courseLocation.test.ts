import { expect, it } from "vitest";
import { readCourseLocation } from "./courseLocation";
it("reads only validated view and millisecond coordinates", () => {
  expect(readCourseLocation({ view: "content", text: "timeline", at: "1234", goal: "private" })).toEqual({ workspace: "content", textView: "timeline", milliseconds: 1234, classic: false });
});
it.each(["-1", "NaN", "1.2", "Infinity", "604800001", "https://media.invalid", ["1", "2"]])("rejects malformed positions %s", at => {
  expect(readCourseLocation({ view: "unknown", text: ["timeline"], at })).toEqual({ workspace: "agent", textView: undefined, milliseconds: 0, classic: false });
});

it.each([undefined, "CLASSIC", ["classic"], "private-answer"])("ignores invalid layout values %s", layout => {
  expect(readCourseLocation(layout === undefined ? {} : { layout }).classic).toBe(false);
});
it("accepts the explicit classic fallback without retaining learning inputs", () => {
  expect(readCourseLocation({ view: "qa", layout: "classic", goal: "PRIVATE", answer: "PRIVATE" })).toEqual({ workspace: "qa", textView: undefined, milliseconds: 0, classic: true });
});
