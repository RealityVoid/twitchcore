#!/usr/bin/env python3
import struct
import glob
from elftools.elf.elffile import ELFFile

regfile = [0]*33
class Regfile:
  def __init__(self):
    self.regs = [0]*33
  def __getitem__(self, key):
    return self.regs[key]
  def __setitem__(self, key, value):
    if key == 0:
      return
    self.regs[key] = value & 0xFFFFFFFF

regfile = Regfile()
PC = 32

from enum import Enum
# RV32I Base Instruction Set
class Ops(Enum):
  LUI = 0b0110111    # load upper immediate
  LOAD = 0b0000011
  STORE = 0b0100011

  AUIPC = 0b0010111  # add upper immediate to pc
  BRANCH = 0b1100011
  JAL = 0b1101111
  JALR = 0b1100111

  IMM = 0b0010011
  OP = 0b0110011

  MISC = 0b0001111
  SYSTEM = 0b1110011

class Funct3(Enum):
  ADD = SUB = ADDI = 0b000
  SLLI = 0b001
  SLT = SLTI = 0b010
  SLTU = SLTIU = 0b011

  XOR = XORI = 0b100
  SRL = SRLI = SRA = SRAI = 0b101
  OR = ORI = 0b110
  AND = ANDI = 0b111

  BEQ = 0b000
  BNE = 0b001
  BLT = 0b100
  BGE = 0b101
  BLTU = 0b110
  BGEU = 0b111

# 64k at 0x80000000
memory = b'\x00'*0x10000

def ws(dat, addr):
  global memory
  #print(hex(addr), len(dat))
  addr -= 0x80000000
  assert addr >=0 and addr < len(memory)
  memory = memory[:addr] + dat + memory[addr+len(dat):]

def r32(addr):
  addr -= 0x80000000
  if addr < 0 or addr >= len(memory):
    raise Exception("read out of bounds: 0x%x" % addr)
  return struct.unpack("<I", memory[addr:addr+4])[0]

def dump():
  pp = []
  for i in range(32):
    if i != 0 and i % 8 == 0:
      pp += "\n"
    pp += " %3s: %08x" % ("x%d" % i, regfile[i])
  pp += "\n  PC: %08x" % regfile[PC]
  print(''.join(pp))

def sign_extend(x, l):
  if x >> (l-1) == 1:
    return -((1 << l) - x)
  else:
    return x

def step():
  # Instruction Fetch
  ins = r32(regfile[PC])
  def gibi(s, e):
    return (ins >> e) & ((1 << (s-e+1))-1)

  # Instruction Decode
  opcode = Ops(gibi(6, 0))
  print("%x %8x %r" % (regfile[PC], ins, opcode))

  if opcode == Ops.JAL:
    # J-type instruction
    rd = gibi(11, 7)
    offset = (gibi(32, 31)<<20) | (gibi(30, 21)<<1) | (gibi(21, 20)<<11) | (gibi(19, 12)<<12)
    print(hex(offset))
    offset = sign_extend(offset, 21)
    print(hex(offset))
    regfile[rd] = regfile[PC] + 4
    regfile[PC] += offset
    return True
  elif opcode == Ops.JALR:
    # I-type instruction
    rd = gibi(11, 7)
    rs1 = gibi(19, 15)
    imm = sign_extend(gibi(31, 20), 12)
    regfile[rd] = regfile[PC] + 4
    regfile[PC] = regfile[rs1] + imm
    return True
  elif opcode == Ops.LUI:
    rd = gibi(11, 7)
    imm = gibi(31, 20)
    # U-type instruction
    regfile[rd] = imm << 12
  elif opcode == Ops.AUIPC:
    # U-type instruction
    rd = gibi(11, 7)
    imm = gibi(31, 20)
    regfile[rd] = regfile[PC] + imm
  elif opcode == Ops.OP:
    # R-type instruction
    rd = gibi(11, 7)
    rs1 = gibi(19, 15)
    rs2 = gibi(24, 20)
    funct3 = Funct3(gibi(14, 12))
    funct7 = gibi(31, 25)
    if funct3 == Funct3.ADD:
      regfile[rd] = regfile[rs1] + regfile[rs2]
    elif funct3 == Funct3.OR:
      regfile[rd] = regfile[rs1] | regfile[rs2]
    else:
      dump()
      raise Exception("write %r funct3 %r" % (opcode, funct3))
  elif opcode == Ops.IMM:
    # I-type instruction
    rd = gibi(11, 7)
    rs1 = gibi(19, 15)
    funct3 = Funct3(gibi(14, 12))
    imm = gibi(31, 20)
    #print(rd, rs1, funct3, imm)
    if funct3 == Funct3.ADDI:
      regfile[rd] = regfile[rs1] + imm
    elif funct3 == Funct3.SLLI:
      regfile[rd] = regfile[rs1] << imm
    elif funct3 == Funct3.SRLI:
      regfile[rd] = regfile[rs1] >> imm
    elif funct3 == Funct3.ORI:
      regfile[rd] = regfile[rs1] | imm
    else:
      dump()
      raise Exception("write %r funct3 %r" % (opcode, funct3))
  elif opcode == Ops.BRANCH:
    # B-type instruction
    rs1 = gibi(19, 15)
    rs2 = gibi(24, 20)
    funct3 = Funct3(gibi(14, 12))
    offset = (gibi(32, 31)<<12) | (gibi(30, 25)<<5) | (gibi(11, 8)<<1) | (gibi(8, 7)<<11)
    offset = sign_extend(offset, 13)
    cond = False
    if funct3 == Funct3.BEQ:
      cond = regfile[rs1] == regfile[rs2]
    elif funct3 == Funct3.BNE:
      cond = regfile[rs1] != regfile[rs2]
    else:
      dump()
      raise Exception("write %r funct3 %r" % (opcode, funct3))
    if cond:
      regfile[PC] += offset
      return True
  elif opcode == Ops.LOAD:
    # I-type instruction
    rd = gibi(11, 7)
    rs1 = gibi(19, 15)
    funct3 = Funct3(gibi(14, 12))
    imm = sign_extend(gibi(31, 20), 12)
    addr = regfile[rs1] + imm
    print("LOAD %8x" % addr)
  elif opcode == Ops.STORE:
    # S-type instruction
    rs1 = gibi(19, 15)
    rs2 = gibi(24, 20)
    width = gibi(14, 12)
    offset = sign_extend(gibi(31, 25)<<5 | gibi(11, 7), 12)
    addr = regfile[rs1] + offset
    value = regfile[rs2]
    print("STORE %8x = %x" % (addr, value))
  elif opcode == Ops.SYSTEM:
    pass
  else:
    dump()
    raise Exception("write op %r" % opcode)

  regfile[PC] += 4
  return True


if __name__ == "__main__":
  for x in glob.glob("riscv-tests/isa/rv32ui-*"):
    if x.endswith('.dump'):
      continue
    with open(x, 'rb') as f:
      print("test", x)
      e = ELFFile(f)
      for s in e.iter_segments():
        ws(s.data(), s.header.p_paddr)
      regfile[PC] = 0x80000000
      while step():
        pass
    break

