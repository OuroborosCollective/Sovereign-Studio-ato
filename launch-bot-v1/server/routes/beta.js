import express from 'express';
import crypto from 'crypto';
import mongoose from 'mongoose';

const router = express.Router();

/**
 * BetaUser Schema definition inside the route for context 
 * (In production, this would typically reside in /models/BetaUser.js)
 */
const betaUserSchema = new mongoose.Schema({
  email: { type: String, required: true, unique: true, lowercase: true, trim: true },
  referralCode: { type: String, unique: true },
  referredBy: { type: String, default: null },
  createdAt: { type: Date, default: Date.now }
});

const BetaUser = mongoose.models.BetaUser || mongoose.model('BetaUser', betaUserSchema);

/**
 * Generiert einen eindeutigen Referral-Code ohne die Verwendung von verbotenen Regex-Operationen.
 */
const createUniqueCode = () => {
  const charset = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'; // No confusing chars like O or 1
  const randomValues = crypto.randomBytes(6);
  let code = '';
  for (let i = 0; i < 6; i++) {
    code += charset.charAt(randomValues[i] % charset.length);
  }
  return code;
};

/**
 * @route   POST /api/beta/signup
 * @desc    Erfasst E-Mails für den Beta-Zugang und generiert Referral-Codes
 */
router.post('/signup', async (req, res) => {
  try {
    const { email, ref } = req.body;

    if (!email || !email.includes('@')) {
      return res.status(400).json({ 
        success: false, 
        error: 'Eine gültige E-Mail-Adresse ist erforderlich.' 
      });
    }

    const existingUser = await BetaUser.findOne({ email });

    if (existingUser) {
      return res.status(200).json({
        success: true,
        message: 'Bereits registriert.',
        referralCode: existingUser.referralCode,
        isNew: false
      });
    }

    let referralCode = createUniqueCode();
    
    // Sicherstellen, dass der Code eindeutig ist
    let isDuplicate = await BetaUser.findOne({ referralCode });
    while (isDuplicate) {
      referralCode = createUniqueCode();
      isDuplicate = await BetaUser.findOne({ referralCode });
    }

    const newUser = new BetaUser({
      email,
      referralCode,
      referredBy: ref || null
    });

    await newUser.save();

    return res.status(201).json({
      success: true,
      message: 'Erfolgreich für die Beta angemeldet.',
      referralCode: newUser.referralCode,
      isNew: true
    });

  } catch (error) {
    return res.status(500).json({ 
      success: false, 
      error: 'Server-Fehler bei der Beta-Registrierung.' 
    });
  }
});

/**
 * @route   GET /api/beta/stats/:code
 * @desc    Gibt die Anzahl der geworbenen Nutzer zurück
 */
router.get('/stats/:code', async (req, res) => {
  try {
    const { code } = req.params;
    const referralCount = await BetaUser.countDocuments({ referredBy: code });
    
    return res.status(200).json({
      success: true,
      referralCount
    });
  } catch (error) {
    return res.status(500).json({ success: false, error: error.message });
  }
});

export default router;