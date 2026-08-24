import unittest
import io
import os
from pathlib import Path
from app.core.crypto_vault import (
    get_vault_kek,
    encrypt_audio_envelope,
    decrypt_audio_bytes,
    decrypt_audio_to_ram
)

class TestCryptoVault(unittest.TestCase):
    def test_vault_kek_generation(self):
        """
        Verifies that the Vault KEK is a 256-bit (32-byte) key.
        """
        kek = get_vault_kek("tenant_test")
        self.assertEqual(len(kek), 32)
        self.assertIsInstance(kek, bytes)

    def test_aes_256_envelope_encryption_cycle(self):
        """
        Verifies full AES-256-GCM envelope encryption & decryption cycle:
        1. Encrypts plaintext audio payload with random DEK.
        2. Wraps DEK with KEK.
        3. Decrypts back and verifies exact byte match.
        """
        sample_audio_payload = b"RIFF....WAVEfmt \x10\x00\x00\x00dataTestAudioStream1234567890"
        org_id = "org_acme_corp"

        # 1. Encrypt
        ciphertext, enc_dek_b64, iv_b64 = encrypt_audio_envelope(sample_audio_payload, org_id)

        self.assertNotEqual(ciphertext, sample_audio_payload)
        self.assertGreater(len(ciphertext), len(sample_audio_payload))
        self.assertIsInstance(enc_dek_b64, str)
        self.assertIsInstance(iv_b64, str)

        # 2. Decrypt in RAM
        decrypted_bytes = decrypt_audio_bytes(ciphertext, enc_dek_b64, iv_b64, org_id)
        self.assertEqual(decrypted_bytes, sample_audio_payload)

    def test_tampered_ciphertext_fails(self):
        """
        Verifies AES-256-GCM authentication tag protection:
        Tampering with any ciphertext byte raises an error.
        """
        sample_payload = b"Confidential Board Meeting Speech"
        ciphertext, enc_dek_b64, iv_b64 = encrypt_audio_envelope(sample_payload)

        # Tamper with 1 byte
        tampered_ciphertext = bytearray(ciphertext)
        tampered_ciphertext[5] ^= 0xFF
        tampered_ciphertext = bytes(tampered_ciphertext)

        with self.assertRaises(Exception):
            decrypt_audio_bytes(tampered_ciphertext, enc_dek_b64, iv_b64)
