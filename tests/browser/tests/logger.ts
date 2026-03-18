import { Logger } from "tslog";

export const log = new Logger({
  name: "notebooks-tests",
  type: process.env.CI ? "json" : "pretty",
});
