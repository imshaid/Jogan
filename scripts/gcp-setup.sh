#!/usr/bin/env bash
# One-time Google Cloud setup for the Jogan API (DECISIONS.md D-022). The owner runs it once,
# from the repo root, logged in to gcloud and gh:  bash scripts/gcp-setup.sh
#
# 1. Copies the Supabase and Gemini values from .env into Secret Manager (never printed) and
#    lets only the API's runtime service account read them.
# 2. Sets up keyless deploys from GitHub Actions: Workload Identity Federation that trusts only
#    the main branch of this repository, and a deployer account that can push images and deploy
#    Cloud Run revisions, nothing else.
# 3. Keeps only the newest images in Artifact Registry.
# 4. Makes the first Cloud Run deploy (public, since the API checks Supabase tokens itself;
#    at most 2 instances) and stores the GitHub repository variables the deploy workflow reads.
# Safe to re-run: existing resources are kept, secrets get a new version.
set -euo pipefail

PROJECT=jogan-510317
PROJECT_NUMBER=923256128150
REGION=asia-southeast1
SERVICE=jogan-api
GITHUB_REPO=imshaid/Jogan
IMAGE=${IMAGE:-$REGION-docker.pkg.dev/$PROJECT/jogan/api:bootstrap}
RUNTIME_SA=jogan-api@$PROJECT.iam.gserviceaccount.com
DEPLOY_SA=jogan-deployer@$PROJECT.iam.gserviceaccount.com
POOL=github
PROVIDER=jogan-repo

[ -f .env ] || { echo "run from the repo root; .env not found" >&2; exit 1; }

env_value() { # the value of $1 in .env, without quotes or a trailing comment
  local line
  line=$(grep -E "^$1=" .env | tail -n 1) || { echo "$1 is missing in .env" >&2; return 1; }
  line=$(printf '%s' "${line#*=}" | sed -E 's/[[:space:]]+#.*$//; s/^[[:space:]]+//; s/[[:space:]]+$//')
  line=$(printf '%s' "$line" | sed -E "s/^\"(.*)\"$/\\1/; s/^'(.*)'$/\\1/")
  [ -n "$line" ] || { echo "$1 is empty in .env" >&2; return 1; }
  printf '%s' "$line"
}

echo "== secrets"
put_secret() { # secret name, .env variable
  local value
  value=$(env_value "$2")
  if ! gcloud secrets describe "$1" --project "$PROJECT" >/dev/null 2>&1; then
    gcloud secrets create "$1" --project "$PROJECT" --replication-policy=automatic --format=none
  fi
  printf '%s' "$value" | gcloud secrets versions add "$1" --project "$PROJECT" --data-file=- --format=none
  gcloud secrets add-iam-policy-binding "$1" --project "$PROJECT" \
    --member="serviceAccount:$RUNTIME_SA" --role=roles/secretmanager.secretAccessor --format=none
  echo "  $1 ← $2"
}
put_secret supabase-url SUPABASE_URL
put_secret supabase-publishable-key SUPABASE_PUBLISHABLE_KEY
put_secret supabase-secret-key SUPABASE_SECRET_KEY
put_secret gemini-api-key GEMINI_API_KEY

echo "== keyless deploys from GitHub Actions"
REPO_ID=$(gh api "repos/$GITHUB_REPO" --jq .id)
if ! gcloud iam workload-identity-pools describe "$POOL" --location=global --project "$PROJECT" >/dev/null 2>&1; then
  gcloud iam workload-identity-pools create "$POOL" --location=global --project "$PROJECT" \
    --display-name="GitHub Actions" --format=none
fi
if ! gcloud iam workload-identity-pools providers describe "$PROVIDER" --location=global \
  --workload-identity-pool="$POOL" --project "$PROJECT" >/dev/null 2>&1; then
  gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" --location=global \
    --workload-identity-pool="$POOL" --project "$PROJECT" --display-name="$GITHUB_REPO main" \
    --issuer-uri=https://token.actions.githubusercontent.com \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository_id=assertion.repository_id,attribute.ref=assertion.ref" \
    --attribute-condition="assertion.repository_id == '$REPO_ID' && assertion.ref == 'refs/heads/main'" \
    --format=none
fi
gcloud iam service-accounts add-iam-policy-binding "$DEPLOY_SA" --project "$PROJECT" \
  --role=roles/iam.workloadIdentityUser --format=none \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL/attribute.repository_id/$REPO_ID"
gcloud projects add-iam-policy-binding "$PROJECT" --role=roles/run.developer \
  --member="serviceAccount:$DEPLOY_SA" --condition=None --format=none
gcloud artifacts repositories add-iam-policy-binding jogan --location="$REGION" --project "$PROJECT" \
  --role=roles/artifactregistry.writer --member="serviceAccount:$DEPLOY_SA" --format=none
gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA" --project "$PROJECT" \
  --role=roles/iam.serviceAccountUser --member="serviceAccount:$DEPLOY_SA" --format=none
echo "  deployer may push images and deploy $SERVICE as $RUNTIME_SA"

echo "== image cleanup (keep the 3 newest)"
policy=$(mktemp)
cat >"$policy" <<'JSON'
[{"name": "keep-recent", "action": {"type": "Keep"}, "mostRecentVersions": {"keepCount": 3}},
 {"name": "delete-older", "action": {"type": "Delete"}, "condition": {"tagState": "any", "olderThan": "1d"}}]
JSON
gcloud artifacts repositories set-cleanup-policies jogan --location="$REGION" --project "$PROJECT" \
  --policy="$policy" --no-dry-run --format=none
rm -f "$policy"

echo "== first deploy of $SERVICE"
gcloud run deploy "$SERVICE" --project "$PROJECT" --region "$REGION" --image "$IMAGE" \
  --service-account "$RUNTIME_SA" --allow-unauthenticated \
  --cpu 1 --memory 1Gi --min-instances 0 --max-instances 2 --cpu-boost \
  --set-secrets "SUPABASE_URL=supabase-url:latest,SUPABASE_PUBLISHABLE_KEY=supabase-publishable-key:latest,SUPABASE_SECRET_KEY=supabase-secret-key:latest" \
  --set-env-vars "JOGAN_CORS_ORIGIN_REGEX=https://jogan[a-z0-9-]*\.vercel\.app" \
  --format=none
URL=$(gcloud run services describe "$SERVICE" --project "$PROJECT" --region "$REGION" --format='value(status.url)')

echo "== GitHub repository variables for the deploy workflow"
gh variable set GCP_WIF_PROVIDER --repo "$GITHUB_REPO" \
  --body "projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL/providers/$PROVIDER"
gh variable set GCP_DEPLOY_SA --repo "$GITHUB_REPO" --body "$DEPLOY_SA"

echo "done. API: $URL"
curl -fsS "$URL/health" && echo
