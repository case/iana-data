import { defineConfig } from "checkly";
import { Frequency } from "checkly/constructs";

export default defineConfig({
  projectName: "ccTLD RDAP Monitoring",
  logicalId: "cctld-rdap-monitoring",
  repoUrl: "https://github.com/case/iana-data",
  checks: {
    activated: true,
    muted: false,
    runtimeId: "2025.04",
    frequency: Frequency.EVERY_24H,
    locations: ["us-west-2"], // Could add "eu-west-3" in the future
    checkMatch: "**/*.check.ts",
  },
  cli: {
    runLocation: "us-west-2",
  },
});
