import { ApiError, userMessage } from "@/lib/api/client";
describe("API error presentation", () => {
  test.each([
    [401, "session expired"],
    [403, "permission"],
    [429, "Too many"],
    [503, "degraded"],
  ])("maps HTTP %i", (status, phrase) => {
    expect(userMessage(new ApiError(status as number, "raw"))).toContain(
      phrase as string,
    );
  });
  test("network errors retain a safe message", () => {
    expect(userMessage(new ApiError(0, "Network unavailable."))).toBe(
      "Network unavailable.",
    );
  });
});
