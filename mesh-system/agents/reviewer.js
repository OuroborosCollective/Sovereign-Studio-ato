export async function reviewer(payload = {}) {
  const blockedPatterns = [
    /github\.com/i,
    /raw\.githubusercontent\.com/i,
    /\.env/i,
    /localhost/i,
    /SUPABASE_SERVICE_ROLE_KEY/i,
    /GEMINI_API_KEY/i,
    /ghp_/i,
    /AIza/i
  ];

  const content = JSON.stringify(payload);

  for (const pattern of blockedPatterns) {
    if (pattern.test(content)) {
      return {
        approved: false,
        reason: `Blocked sensitive pattern: ${pattern}`
      };
    }
  }

  return {
    approved: true,
    reason: 'Content passed reviewer gate'
  };
}
