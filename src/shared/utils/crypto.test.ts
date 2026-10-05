import { describe, expect, it } from 'vitest';
import { maskSecrets } from './crypto';

describe('maskSecrets', () => {
  it('masks GitHub Classic PATs', () => {
    const secret = 'ghp_1234567890abcdefghijklmnopqrstuvwx';
    const text = `Error: Failed to use token ${secret}`;
    expect(maskSecrets(text)).toBe('Error: Failed to use token ghp_****');
  });

  it('masks GitHub Fine-grained PATs', () => {
    const secret = 'github_pat_11AABCXYZ0123456789012_abcdefghijklmnopqrstuvwxyz012345678901234567890123456789012345678';
    const text = `Could not authenticate with ${secret}`;
    expect(maskSecrets(text)).toBe('Could not authenticate with github_pat_****');
  });

  it('masks GitHub token variants', () => {
    expect(maskSecrets('gho_1234567890abcdefghijklmnopqrstuvwx')).toBe('gho_****');
    expect(maskSecrets('ghu_1234567890abcdefghijklmnopqrstuvwx')).toBe('ghu_****');
    expect(maskSecrets('ghs_1234567890abcdefghijklmnopqrstuvwx')).toBe('ghs_****');
    expect(maskSecrets('ghr_1234567890abcdefghijklmnopqrstuvwx')).toBe('ghr_****');
  });

  it('masks Google API keys', () => {
    const secret = 'AIzaSyA-1234567890_abcdefghijklmnopqrst';
    const text = `API key ${secret} is invalid`;
    expect(maskSecrets(text)).toBe('API key AIza**** is invalid');
    expect(maskSecrets('AIza_anything_long_enough_abcdefghijklmnopqrstuv')).toBe('AIza****');
  });

  it('masks OpenRouter style keys', () => {
    const secret = 'sk-or-v1-abcdefghijklmnopqrstuvwxyz0123456789';
    expect(maskSecrets(`Using ${secret}`)).toBe('Using sk-or-v1-****');
  });

  it('masks HuggingFace, Together AI and Pollinations AI keys', () => {
    expect(maskSecrets('hf_abcdefghijklmnopqrstuvwxyz')).toBe('hf_****');
    expect(maskSecrets('together_abcdefghijklmnopqrstuvwxyz')).toBe('together_****');
    expect(maskSecrets('pollinations_abcdefghijklmnopqrstuvwxyz')).toBe('pollinations_****');
  });

  it('masks Bearer tokens', () => {
    const secret = 'Bearer ya29.a0AfB_ByD_E-fGhIjKlMnOpQrStUvWxYz1234567890';
    const text = `Authorization: ${secret}`;
    expect(maskSecrets(text)).toBe('Authorization: Bearer ****');
  });

  it('masks Anthropic style keys', () => {
    const secret = 'sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789abcdefghijklmnopqrstuvwxyz01';
    expect(maskSecrets(`Using ${secret}`)).toBe('Using sk-ant-****');
  });

  it('masks Groq style keys', () => {
    const secret = 'gsk_abcdefghijklmnopqrstuvwxyz0123456789';
    expect(maskSecrets(`Failed with ${secret}`)).toBe('Failed with gsk_****');
  });

  it('masks xAI style keys', () => {
    const secret = 'xai-1234567890abcdefghijklmnopqrstuvwxyz';
    expect(maskSecrets(`Failed with ${secret}`)).toBe('Failed with xai-****');
  });

  it('masks OpenAI Project keys', () => {
    const secret = 'sk-proj-abcdefghijklmnopqrstuvwxyz0123456789abcdefghijklmnopqrstuvwxyz01';
    expect(maskSecrets(`Using ${secret}`)).toBe('Using sk-proj-****');
  });

  it('masks long OpenAI Project keys without leaking suffixes', () => {
    const credentialBody = `${'a'.repeat(140)}_${'Z'.repeat(40)}-tail`;
    const secret = `sk-proj-${credentialBody}`;
    const masked = maskSecrets(`Using ${secret}; next field`);

    expect(masked).toBe('Using sk-proj-****; next field');
    expect(masked).not.toContain('tail');
    expect(masked).not.toContain('ZZZZ');
  });

  it('masks label-based credentials', () => {
    expect(maskSecrets('password: my-secret-password')).toBe('password: ****');
    expect(maskSecrets('passwd=some-pass')).toBe('passwd=****');
    expect(maskSecrets('token=ghp_12345')).toBe('token=****');
    expect(maskSecrets('api_key=abcdefghijklmnopqrstuvwxyz1234567890')).toBe('api_key=****');
    expect(maskSecrets('access-token=abcdefghijklmnopqrstuvwxyz1234567890')).toBe('access-token=****');
    expect(maskSecrets('private_key=abcdefghijklmnopqrstuvwxyz1234567890')).toBe('private_key=****');
    expect(maskSecrets('secret: somevalue')).toBe('secret: ****');
    expect(maskSecrets('client_secret: client_secret_value_123')).toBe('client_secret: ****');
    expect(maskSecrets('refresh_token: refresh_token_val_456')).toBe('refresh_token: ****');
    expect(maskSecrets('auth_token=auth_token_val_789')).toBe('auth_token=****');
    expect(maskSecrets('id_token=id_token_val_101')).toBe('id_token=****');
    expect(maskSecrets('api_secret: api_secret_val_202')).toBe('api_secret: ****');
    expect(maskSecrets('client_id: client_id_12345')).toBe('client_id: ****');
    expect(maskSecrets('session_token=session_token_67890')).toBe('session_token=****');
    expect(maskSecrets('session_id: sess_123456789')).toBe('session_id: ****');
    expect(maskSecrets('webhook_secret: hook_secret_123')).toBe('webhook_secret: ****');
    expect(maskSecrets('webhook-token=hook_token_456')).toBe('webhook-token=****');
    expect(maskSecrets('webhook_key: hook_key_789')).toBe('webhook_key: ****');
    expect(maskSecrets('ssh_private_key=ssh_private_material_123')).toBe('ssh_private_key=****');
    expect(maskSecrets('ssh-key: ssh_key_material_456')).toBe('ssh-key: ****');
    expect(maskSecrets('signing_key=signing_material_789')).toBe('signing_key=****');
    expect(maskSecrets('signing-secret: signing_secret_101')).toBe('signing-secret: ****');
    expect(maskSecrets('admin_key: admin_key_material_202')).toBe('admin_key: ****');
    expect(maskSecrets('admin-secret=admin_secret_material_303')).toBe('admin-secret=****');
    expect(maskSecrets('admin_token=admin_token_material_404')).toBe('admin_token=****');
    expect(maskSecrets('auth_key: auth_key_material_505')).toBe('auth_key: ****');
    expect(maskSecrets('access_secret=access_secret_material_606')).toBe('access_secret=****');
    expect(maskSecrets('account_key: acc_key_val_12345')).toBe('account_key: ****');
    expect(maskSecrets('account_secret: acc_sec_val_67890')).toBe('account_secret: ****');
    expect(maskSecrets('account-key=acc_key_val_99999')).toBe('account-key=****');
    expect(maskSecrets('database_password: db_secret_pass_123')).toBe('database_password: ****');
    expect(maskSecrets('db_password=db_secret_pass_456')).toBe('db_password=****');
    expect(maskSecrets('db_pass: db_secret_pass_789')).toBe('db_pass: ****');
    expect(maskSecrets('master_password=master_pass_101')).toBe('master_password=****');
    expect(maskSecrets('master_key: master_key_val_202')).toBe('master_key: ****');
    expect(maskSecrets('secret_key=secret_key_val_303')).toBe('secret_key=****');
    expect(maskSecrets('encryption_secret: enc_secret_val_404')).toBe('encryption_secret: ****');
    expect(maskSecrets('cipher_key=cipher_key_val_505')).toBe('cipher_key=****');
    expect(maskSecrets('deploy_key: deploy_key_val_606')).toBe('deploy_key: ****');
    expect(maskSecrets('encryption_key=encryption_key_val_707')).toBe('encryption_key=****');
    expect(maskSecrets('bot_token: bot_token_val_808')).toBe('bot_token: ****');
    expect(maskSecrets('passphrase=passphrase_val_909')).toBe('passphrase=****');
    expect(maskSecrets('oauth_token: oauth_token_val_111')).toBe('oauth_token: ****');
    expect(maskSecrets('oauth_secret=oauth_secret_val_222')).toBe('oauth_secret=****');
    expect(maskSecrets('auth_secret: auth_secret_val_333')).toBe('auth_secret: ****');
    expect(maskSecrets('bearer_token=bearer_token_val_444')).toBe('bearer_token=****');
    expect(maskSecrets('registration_token: reg_token_val_555')).toBe('registration_token: ****');
    expect(maskSecrets('access_key_id=AKIAIOSFODNN7EXAMPLE')).toBe('access_key_id=****');
    expect(maskSecrets('aws_secret_access_key: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY')).toBe('aws_secret_access_key: ****');
    expect(maskSecrets('tenant_secret: tenant_sec_val_101')).toBe('tenant_secret: ****');
    expect(maskSecrets('tenant_key=tenant_key_val_202')).toBe('tenant_key=****');
    expect(maskSecrets('license_key: lic_key_val_303')).toBe('license_key: ****');
    expect(maskSecrets('license_secret=lic_sec_val_404')).toBe('license_secret=****');
    expect(maskSecrets('org_key: org_key_val_505')).toBe('org_key: ****');
    expect(maskSecrets('org_secret=org_sec_val_606')).toBe('org_secret=****');
    expect(maskSecrets('private_key_passphrase: my_secret_passphrase')).toBe('private_key_passphrase: ****');
    expect(maskSecrets('key_passphrase=my_key_passphrase_123')).toBe('key_passphrase=****');
    expect(maskSecrets('sendgrid_key: sg_secret_val_101')).toBe('sendgrid_key: ****');
    expect(maskSecrets('resend_key=resend_secret_val_202')).toBe('resend_key=****');
    expect(maskSecrets('mailgun_key: mailgun_secret_val_303')).toBe('mailgun_key: ****');
    expect(maskSecrets('postmark_key=postmark_secret_val_404')).toBe('postmark_key=****');
    expect(maskSecrets('twilio_key: twilio_key_val_505')).toBe('twilio_key: ****');
    expect(maskSecrets('twilio_secret=twilio_secret_val_606')).toBe('twilio_secret=****');
  });

  it('masks quoted label-based credentials and base64 characters', () => {
    expect(maskSecrets('"password": "my-secret-password"')).toBe('"password": ****');
    expect(maskSecrets("'api_key': 'abc123+/~='")).toBe("'api_key': ****");
    expect(maskSecrets('token: value_with_@#$%^&*')).toBe('token: ****');
  });

  it('masks common communication-provider env labels without masking plain provider text', () => {
    expect(maskSecrets('SENDGRID_API_KEY=sg_env_value_101')).toBe('SENDGRID_API_KEY=****');
    expect(maskSecrets('RESEND_API_KEY=resend_env_value_202')).toBe('RESEND_API_KEY=****');
    expect(maskSecrets('MAILGUN_API_KEY=mailgun_env_value_303')).toBe('MAILGUN_API_KEY=****');
    expect(maskSecrets('POSTMARK_SERVER_TOKEN=postmark_env_value_404')).toBe('POSTMARK_SERVER_TOKEN=****');
    expect(maskSecrets('TWILIO_AUTH_TOKEN=twilio_env_value_505')).toBe('TWILIO_AUTH_TOKEN=****');
    expect(maskSecrets('TWILIO_API_SECRET=twilio_env_value_606')).toBe('TWILIO_API_SECRET=****');

    const plain = 'sendgrid_key rotation docs mention resend_key and twilio_secret without assignments';
    expect(maskSecrets(plain)).toBe(plain);
  });

  it('masks AI, vector DB and cloud provider credential labels without masking unassigned label mentions', () => {
    expect(maskSecrets('cohere_key: cohere_key_val_101')).toBe('cohere_key: ****');
    expect(maskSecrets('cohere_secret=cohere_secret_val_202')).toBe('cohere_secret=****');
    expect(maskSecrets('cohere_token: cohere_token_val_303')).toBe('cohere_token: ****');
    expect(maskSecrets('pinecone_key=pinecone_key_val_404')).toBe('pinecone_key=****');
    expect(maskSecrets('pinecone_secret: pinecone_secret_val_505')).toBe('pinecone_secret: ****');
    expect(maskSecrets('qdrant_key=qdrant_key_val_606')).toBe('qdrant_key=****');
    expect(maskSecrets('qdrant_secret: qdrant_secret_val_707')).toBe('qdrant_secret: ****');
    expect(maskSecrets('deepseek_key: deepseek_key_val_707')).toBe('deepseek_key: ****');
    expect(maskSecrets('deepseek_secret=deepseek_secret_val_808')).toBe('deepseek_secret=****');
    expect(maskSecrets('deepseek_token: deepseek_token_val_909')).toBe('deepseek_token: ****');
    expect(maskSecrets('perplexity_key=perplexity_key_val_111')).toBe('perplexity_key=****');
    expect(maskSecrets('perplexity_secret: perplexity_secret_val_222')).toBe('perplexity_secret: ****');
    expect(maskSecrets('replicate_key=replicate_key_val_333')).toBe('replicate_key=****');
    expect(maskSecrets('replicate_secret: replicate_secret_val_444')).toBe('replicate_secret: ****');
    expect(maskSecrets('cloudflare_token=cloudflare_token_val_555')).toBe('cloudflare_token=****');
    expect(maskSecrets('cloudflare_key: cloudflare_key_val_666')).toBe('cloudflare_key: ****');
    expect(maskSecrets('cloudflare_secret=cloudflare_secret_val_777')).toBe('cloudflare_secret=****');
    expect(maskSecrets('"deepseek_key": "quoted_value_123"')).toBe('"deepseek_key": ****');

    const plain = 'cohere_key docs mention pinecone_secret, qdrant_key, deepseek_key, perplexity_secret, replicate_key and cloudflare_token without assignments';
    expect(maskSecrets(plain)).toBe(plain);
  });

  it('masks multiple secrets in one string', () => {
    const text = 'Keys: ghp_1234567890abcdefghijklmnopqrstuvwx and AIzaSyA-1234567890_abcdefghijklmnopqrst';
    expect(maskSecrets(text)).toBe('Keys: ghp_**** and AIza****');
  });

  it('leaves normal text untouched', () => {
    const text = 'This is a normal error message with no secrets.';
    expect(maskSecrets(text)).toBe(text);
  });

  it('handles empty or null input', () => {
    expect(maskSecrets('')).toBe('');
    // @ts-ignore
    expect(maskSecrets(null)).toBe(null);
  });
});
