import express from 'express';
const router = express.Router();
import User from '../models/User.js';

/**
 * Validiert einen Referral-Code auf Existenz und Verfügbarkeit.
 * POST /api/referral/validate
 */
router.post('/validate', async (req, res) => {
  try {
    const { referralCode } = req.body;

    if (!referralCode) {
      return res.status(400).json({ 
        success: false, 
        error: 'Referral-Code ist erforderlich.' 
      });
    }

    const inviter = await User.findOne({ referralCode: referralCode.trim() });

    if (!inviter) {
      return res.status(404).json({ 
        success: false, 
        error: 'Der angegebene Code ist ungültig.' 
      });
    }

    return res.status(200).json({
      success: true,
      data: {
        inviterId: inviter._id,
        inviterName: inviter.username || 'Ein Sovereign-Nutzer'
      }
    });
  } catch (error) {
    return res.status(500).json({ 
      success: false, 
      error: 'Interner Serverfehler bei der Code-Validierung.' 
    });
  }
});

/**
 * Verknüpft einen neuen User mit einem Inviter und inkrementiert den Zähler.
 * POST /api/referral/track
 */
router.post('/track', async (req, res) => {
  try {
    const { userId, referralCode } = req.body;

    if (!userId || !referralCode) {
      return res.status(400).json({ 
        success: false, 
        error: 'User-ID und Referral-Code fehlen.' 
      });
    }

    const inviter = await User.findOne({ referralCode: referralCode.trim() });
    const targetUser = await User.findById(userId);

    if (!inviter || !targetUser) {
      return res.status(404).json({ 
        success: false, 
        error: 'Referenz-Objekte nicht gefunden.' 
      });
    }

    if (targetUser.referredBy) {
      return res.status(400).json({ 
        success: false, 
        error: 'User wurde bereits über ein Referral registriert.' 
      });
    }

    if (inviter._id.toString() === targetUser._id.toString()) {
      return res.status(400).json({ 
        success: false, 
        error: 'Selbst-Referral ist nicht zulässig.' 
      });
    }

    // Atomares Update der Referral-Logik
    targetUser.referredBy = inviter._id;
    await targetUser.save();

    await User.findByIdAndUpdate(inviter._id, {
      $inc: { 'stats.referralCount': 1 },
      $push: { 'stats.invitedUsers': targetUser._id }
    });

    return res.status(200).json({
      success: true,
      message: 'Referral-Tracking erfolgreich abgeschlossen.'
    });
  } catch (error) {
    return res.status(500).json({ 
      success: false, 
      error: 'Fehler beim Tracking des Referrals.' 
    });
  }
});

/**
 * Ruft den aktuellen Referral-Status eines Users ab.
 * GET /api/referral/stats/:userId
 */
router.get('/stats/:userId', async (req, res) => {
  try {
    const { userId } = req.params;
    const user = await User.findById(userId).select('referralCode stats.referralCount');

    if (!user) {
      return res.status(404).json({ 
        success: false, 
        error: 'User nicht gefunden.' 
      });
    }

    return res.status(200).json({
      success: true,
      data: {
        code: user.referralCode,
        totalInvites: user.stats?.referralCount || 0
      }
    });
  } catch (error) {
    return res.status(500).json({ 
      success: false, 
      error: 'Statistiken konnten nicht geladen werden.' 
    });
  }
});

export default router;