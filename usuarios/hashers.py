"""Verifica las contraseñas bcrypt migradas de Supabase Auth ($2a$/$2b$).

El hash se guarda como 'supabase_bcrypt$<hash original>'. Como no es el hasher
preferido, Django re-hashea la contraseña con PBKDF2 en el primer login exitoso.
"""

import bcrypt
from django.contrib.auth.hashers import BasePasswordHasher, mask_hash
from django.utils.crypto import constant_time_compare


class SupabaseBcryptHasher(BasePasswordHasher):
    algorithm = "supabase_bcrypt"

    @classmethod
    def desde_supabase(cls, hash_bcrypt: str) -> str:
        return f"{cls.algorithm}${hash_bcrypt}"

    def _hash_original(self, encoded: str) -> str:
        algoritmo, hash_bcrypt = encoded.split("$", 1)
        assert algoritmo == self.algorithm
        return hash_bcrypt

    def verify(self, password, encoded):
        hash_bcrypt = self._hash_original(encoded).encode()
        try:
            calculado = bcrypt.hashpw(password.encode(), hash_bcrypt)
        except ValueError:  # contraseña de más de 72 bytes o hash corrupto
            return False
        return constant_time_compare(calculado, hash_bcrypt)

    def encode(self, password, salt):
        raise NotImplementedError("Solo verifica contraseñas migradas; no genera hashes nuevos.")

    def decode(self, encoded):
        hash_bcrypt = self._hash_original(encoded)
        return {"algorithm": self.algorithm, "hash": hash_bcrypt[29:], "salt": hash_bcrypt[:29]}

    def safe_summary(self, encoded):
        datos = self.decode(encoded)
        return {"algoritmo": self.algorithm, "salt": mask_hash(datos["salt"]), "hash": mask_hash(datos["hash"])}

    def must_update(self, encoded):
        return True

    def harden_runtime(self, password, encoded):
        pass
