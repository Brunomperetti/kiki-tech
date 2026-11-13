import { ConnectionCenter } from "../integration/ConnectionCenter";
import type { Item } from "./operations-model";
import { demoListings } from "./commercial-demo";

export function DemoConnections({ rows }: { rows: Item[] }) {
  const ml = demoListings(rows, "ml"),
    tn = demoListings(rows, "tn");
  return (
    <ConnectionCenter
      demo
      data={{
        synthetic: true,
        external_writes_enabled: false,
        actions_enabled: false,
        external_oauth_allowed: false,
        max_csv_bytes: 15 * 1024 * 1024,
        ecomm: {
          api_configured: false,
          configured: false,
          live_authorization_verified: false,
          last_successful_capture_at: null,
          last_successful_complete: true,
          last_successful_variants: rows.length,
          refresh_in_progress: false,
          refresh_job: null,
          schedule_times: ["08:25", "16:25"],
          schedule_timezone: "America/Argentina/Buenos_Aires",
          next_updates: [],
          github_schedule_verified: false,
        },
        ml: {
          connected: false,
          user_id: null,
          token_expired: false,
          token_expiration: null,
          last_sync: ml.captured_at,
          listing_count: ml.total_records,
          publication_count: ml.distinct_publications,
        },
        tn: {
          source: "TIENDANUBE_CSV",
          available: true,
          imported_at: tn.captured_at,
          records: tn.total_records,
          products: null,
          current_publication_verified: false,
        },
      }}
    />
  );
}
