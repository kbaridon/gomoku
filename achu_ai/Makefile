NAME		:= achu_ai
CXX			:= g++
CXXFLAGS	:= -Wall -Wextra -std=c++23 -MMD -MP
CPPFLAGS	:= -Iinclude

SRC_DIR		:= src
OBJ_DIR		:= obj

SRC_FILES	:=	main.cpp \
				Board.cpp \
				Player.cpp \
				Game.cpp

SRCS	:= $(addprefix $(SRC_DIR)/,$(SRC_FILES))
OBJS	:= $(SRCS:$(SRC_DIR)/%.cpp=$(OBJ_DIR)/%.o)
DEPS	:= $(OBJS:.o=.d)

.PHONY: all clean fclean re

all: $(NAME)

$(NAME): $(OBJS)
	$(CXX) $(OBJS) -o $(NAME)

$(OBJ_DIR)/%.o: $(SRC_DIR)/%.cpp
	@mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS) $(CPPFLAGS) -c $< -o $@

clean:
	rm -rf $(OBJ_DIR)

fclean: clean
	rm -f $(NAME)

re: fclean all

-include $(DEPS)