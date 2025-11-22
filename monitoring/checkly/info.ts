import * as path from "path";
import * as fs from "fs";

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

// Count checks
const totalServers = data.ccTldRdapServers.length;
const activeServers = data.ccTldRdapServers.filter((s) => s.monitoring).length;
const checksPerServer = 2; // 404 and 200 checks
const totalChecks = totalServers * checksPerServer;
const activeChecks = activeServers * checksPerServer;

// Frequency: EVERY_24H = once per day
const frequencyHours = 24;
const checksPerDay = activeChecks;
const checksPerMonth = checksPerDay * 30;

// Locations: 2 (us-west-2, eu-west-3)
const locations = 2;
const totalRunsPerMonth = checksPerMonth * locations;

console.log("Checkly Configuration Info");
console.log("==========================");
console.log(`Total servers: ${totalServers}`);
console.log(`Active servers (monitoring: true): ${activeServers}`);
console.log(`Checks per server: ${checksPerServer} (404 + 200)`);
console.log(`Total checks: ${totalChecks}`);
console.log(`Active checks: ${activeChecks}`);
console.log();
console.log(`Frequency: Every ${frequencyHours} hours`);
console.log(`Locations: ${locations}`);
console.log();
console.log(`Check runs per day: ${checksPerDay * locations}`);
console.log(`Check runs per month: ${totalRunsPerMonth.toLocaleString()}`);
