import { notificationPath } from "@/lib/notifications/push";
import { loginSchema, reportSchema, watchSchema } from "@/lib/validation/forms";

describe("mobile safety contracts", () => {
  test("deep links target the entity screen", () => {
    expect(notificationPath({ alert_id: "a-1" })).toBe("/(citizen)/alerts/a-1");
    expect(notificationPath({ report_id: "r-1" })).toBe(
      "/(citizen)/reports/r-1",
    );
    expect(notificationPath({ task_id: "t-1" })).toBe("/(responder)/tasks/t-1");
  });

  test("report validation rejects incomplete evidence metadata", () => {
    expect(
      reportSchema.safeParse({
        category: "FLOODING",
        severity: "HIGH",
        description: "short",
        latitude: 19,
        longitude: 72,
      }).success,
    ).toBe(false);
    expect(
      reportSchema.safeParse({
        category: "FLOODING",
        severity: "HIGH",
        description: "Road is covered by water",
        latitude: 19,
        longitude: 72,
      }).success,
    ).toBe(true);
  });

  test("login and watch-location validation are bounded", () => {
    expect(
      loginSchema.safeParse({
        identifier: "citizen",
        password: "safe",
        role: "CITIZEN",
      }).success,
    ).toBe(true);
    expect(
      watchSchema.safeParse({
        label: "Home",
        latitude: 190,
        longitude: 72,
        risk_threshold: "HIGH",
        notify_push: true,
      }).success,
    ).toBe(false);
  });
});
