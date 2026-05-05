import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import dotenv from 'dotenv';

// Import local route handlers
import betaRoutes from './routes/beta.js';
import referralRoutes from './routes/referral.js';

dotenv.config();

const app = express();
const PORT = process.env.PORT || 3001;

/**
 * SOVEREIGN STUDIO - HYBRID BACKEND CORE
 * Express entrypoint optimized for Gemini-API orchestrated workflows
 */

// Global Security Middleware
app.use(helmet());
app.use(cors({
  origin: process.env.ALLOWED_ORIGINS ? process.env.ALLOWED_ORIGINS.split(',') : '*',
  methods: ['GET', 'POST', 'PATCH', 'DELETE'],
  credentials: true
}));

// Standard Parsers
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ extended: true, limit: '50mb' }));

// Traceability Middleware for AI-Operations
app.use((req, res, next) => {
  const traceId = req.headers['x-sovereign-trace-id'] || Math.random().toString(36).substring(7);
  req.traceId = traceId;
  next();
});

// Base Health Check for CI/CD Pipeline
app.get('/api/status', (req, res) => {
  res.status(200).json({
    status: 'online',
    version: '1.0.0-beta',
    engine: 'Sovereign Studio Design-Coder',
    timestamp: new Date().toISOString()
  });
});

// Feature Routes
app.use('/api/beta', betaRoutes);
app.use('/api/referral', referralRoutes);

// Global Error Handler for Cross-Platform Integrity
app.use((err, req, res, next) => {
  console.error(`[SERVER ERROR][${req.traceId}]:`, err.message);
  res.status(err.status || 500).json({
    success: false,
    error: err.message || 'Internal Hybrid Engine Error',
    traceId: req.traceId
  });
});

app.listen(PORT, () => {
  console.log(`[SOVEREIGN STUDIO] Backend operational on port ${PORT}`);
});

export default app;