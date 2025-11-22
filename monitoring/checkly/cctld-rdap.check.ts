import * as path from "path";
import * as fs from "fs";
import {
  ApiCheck,
  AssertionBuilder,
  CheckGroupV2,
  Dashboard,
  RetryStrategyBuilder,
} from "checkly/constructs";

const group = new CheckGroupV2("cctld-rdap", {
  name: "ccTLD RDAP",
  retryStrategy: RetryStrategyBuilder.exponentialStrategy({
    maxRetries: 5,
    baseBackoffSeconds: 10,
    sameRegion: false,
  }),
});

interface CcTldRdapServer {
  tld: string;
  rdapServer: string;
  backendOperator: string;
  dateUpdated: string;
  source: string;
  notes: string;
  monitoring: boolean;
}

interface SupplementalData {
  ccTldRdapServers: CcTldRdapServer[];
}

// Read the supplemental ccTLD RDAP data
const dataPath = path.join(
  __dirname,
  "../../data/manual/supplemental-cctld-rdap.json",
);
const data: SupplementalData = JSON.parse(fs.readFileSync(dataPath, "utf-8"));

// Create API checks for each server
// The monitoring field controls whether the check is activated
for (const server of data.ccTldRdapServers) {
  const { tld, rdapServer, backendOperator, monitoring } = server;
  const operatorTag = `operator-${
    backendOperator.toLowerCase().replace(/ /g, "-")
  }`;

  // Check for known domain - should return 200 with valid RDAP domain response
  new ApiCheck(`${tld}-200`, {
    name: `${tld}-200`,
    group,
    activated: monitoring,
    tags: ["cctld-rdap", operatorTag],
    request: {
      method: "GET",
      url: `${rdapServer}domain/nic.${tld}`,
      assertions: [
        AssertionBuilder.statusCode().equals(200),
        AssertionBuilder.headers("content-type").contains(
          "application/rdap+json",
        ),
        AssertionBuilder.jsonBody("$.objectClassName").equals("domain"),
      ],
    },
  });
}

// Collect unique operator tags for the dashboard
const operatorTags = [
  ...new Set(
    data.ccTldRdapServers.map(
      (s) => `operator-${s.backendOperator.toLowerCase().replace(/ /g, "-")}`,
    ),
  ),
];

new Dashboard("cctld-rdap-dashboard", {
  customUrl: "cctld-rdap",
  header: "ccTLD RDAP Status",
  description:
    "Monitoring 200s from ccTLD RDAP servers that aren't in the IANA RDAP bootstrap file.",
  tags: ["cctld-rdap", ...operatorTags],
  checksPerPage: 20,
  width: "FULL",
});
