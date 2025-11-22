import * as path from "path";
import * as fs from "fs";
import config from "./checkly.config.ts";

interface CcTldRdapServer {
  tld: string;
  monitoring: boolean;
}

interface SupplementalData {
  ccTldRdapServers: CcTldRdapServer[];
}

const dataPath = path.join(
  __dirname,
  "../../data/manual/supplemental-cctld-rdap.json",
);
const data: SupplementalData = JSON.parse(fs.readFileSync(dataPath, "utf-8"));

// Get config values
const frequency = config.checks?.frequency as { frequency: number };
const frequencyMinutes = frequency?.frequency ?? 1440; // default 24h
const locations = config.checks?.locations ?? [];

// Count checks
const totalServers = data.ccTldRdapServers.length;
const activeServers = data.ccTldRdapServers.filter((s) => s.monitoring).length;
const checksPerServer = 1; // 200 check only
const totalChecks = totalServers * checksPerServer;
const activeChecks = activeServers * checksPerServer;

// Calculate runs
const runsPerDay = (24 * 60) / frequencyMinutes;
const checksPerDay = activeChecks * runsPerDay;
const checksPerMonth = checksPerDay * 30;
const totalRunsPerMonth = checksPerMonth * locations.length;

console.log("Checkly Configuration Info");
console.log("==========================");
console.log(`Total servers: ${totalServers}`);
console.log(`Active servers (monitoring: true): ${activeServers}`);
console.log(`Checks per server: ${checksPerServer} (404 + 200)`);
console.log(`Total checks: ${totalChecks}`);
console.log(`Active checks: ${activeChecks}`);
console.log();
console.log(`Frequency: Every ${frequencyMinutes} minutes (${frequencyMinutes / 60} hours)`);
console.log(`Locations: ${locations.length} (${locations.join(", ")})`);
console.log();
console.log(`Check runs per day: ${(checksPerDay * locations.length).toLocaleString()}`);
console.log(`Check runs per month: ${totalRunsPerMonth.toLocaleString()}`);
