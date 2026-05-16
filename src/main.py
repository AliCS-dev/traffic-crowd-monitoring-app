from image_input import load_input_image


def main():
    image_path = "data/input/sample_image.jpg"
    image = load_input_image(image_path)

    print("Image is ready for the next processing step.")


if __name__ == "__main__":
    main()