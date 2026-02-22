import os
import math

def split_targets(num_chunks=5):
    base_path = os.path.dirname(os.path.abspath(__file__))
    source_file = os.path.join(base_path, "quickstrike_targets.txt")
    
    if not os.path.exists(source_file):
        print("Error: quickstrike_targets.txt not found.")
        return

    with open(source_file, 'r') as f:
        lines = [line.strip() for line in f if line.strip()]

    total = len(lines)
    chunk_size = math.ceil(total / num_chunks)
    
    print(f"Splitting {total} targets into {num_chunks} files of approx {chunk_size} lines.")

    for i in range(num_chunks):
        chunk = lines[i*chunk_size : (i+1)*chunk_size]
        filename = f"quickstrike_targets_{i+1}.txt"
        output_path = os.path.join(base_path, filename)
        
        with open(output_path, 'w') as out:
            for line in chunk:
                out.write(f"{line}\n")
        
        print(f"Created {filename} with {len(chunk)} targets.")

if __name__ == "__main__":
    split_targets()